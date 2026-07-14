"""The Orchestrator's main loop (docs/agent/AGENT_VISION.md §3, §7, §9):
Planner -> (step-prep -> prompt_builder -> context_builder -> subagent_builder
-> subagent.run -> state.append -> Monitor) per step -> repeat, re-invoking
the Planner with the updated state, until the plan is judged complete ->
Synthesis.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.orchestrator.parallel_dispatch import dispatch_layer_concurrently
from app.agent_core.orchestrator.replan_ledger import ReplanLedger
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.planner import build_next_plan_steps
from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStep, ReplanFocus, RoleName
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning_effort import TurnReasoningConfig
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.synthesis.synthesis import compose_answer
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry

DEFAULT_MAX_PLANNER_INVOCATIONS = 5


async def run_plan_to_completion(
    *,
    user_goal: str,
    original_user_message: str,
    user_id: str,
    llm_adapter: LLMAdapter,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    plan_id: str,
    max_planner_invocations: int = DEFAULT_MAX_PLANNER_INVOCATIONS,
    reasoning_config: TurnReasoningConfig | None = None,
    sub_asks: list[str] | None = None,
    constraints: list[str] | None = None,
    open_questions: list[str] | None = None,
    implies_action_request: bool = False,
    streaming_queue: asyncio.Queue[str] | None = None,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    replan_ledger: ReplanLedger | None = None,
) -> tuple[PlanExecutionState, StateEntry | None, str | None]:
    """Drives one full turn: adaptive planning + per-step dispatch + Synthesis.

    Returns `(state, None, clarification_question)` when the plan never
    reached `plan_status="complete"` -- the caller must treat a `None` final
    entry as "no answer yet," not a crash. `clarification_question` is the
    real question text when the plan is blocked on a genuine ambiguity, else
    `None` (e.g. the invocation budget simply ran out). Otherwise returns
    `(state, final_entry, None)`: the final `StateEntry` to compose the
    answer from (a composition-role step's own entry if the Planner ended
    the plan with one, else a synthesis fallback entry -- see below).
    """
    state = PlanExecutionState(plan_id=plan_id)
    monitor_flags: list[str] = []
    replan_reason: str | None = None
    replan_focus: ReplanFocus | None = None
    plan_status = "in_progress"
    clarification_question: str | None = None

    _max_invocations = reasoning_config.max_planner_invocations if reasoning_config else max_planner_invocations
    for invocation in range(1, _max_invocations + 1):
        # On the last available round, tell the Planner to conclude (compose or
        # clarify) rather than schedule more exploration -- otherwise a turn
        # that keeps re-trying an unresolvable/ambiguous entity simply exhausts
        # the budget and returns nothing. Carried on its own `final_round`
        # field, NOT in monitor_flags, so the council's adaptive-depth gate
        # doesn't misread a wrap-up as a replan (see planner schema).
        planner_input = PlannerInvocationInput(
            user_goal=user_goal,
            original_user_message=original_user_message,
            sub_asks=sub_asks or [],
            constraints=constraints or [],
            open_questions=open_questions or [],
            implies_action_request=implies_action_request,
            state_index=build_state_index(state.entries),
            plan_graph_so_far=state.plan_graph,
            monitor_flags=monitor_flags,
            replan_reason=replan_reason,
            unresolvable_entities=unresolvable_registry.snapshot() if unresolvable_registry else [],
            final_round=(invocation == _max_invocations),
            # Objectives re-attempted past the replan threshold and still
            # failing -- the Planner is told not to reschedule equivalent work
            # for these (§4.1). Kept off monitor_flags for the same council-gate
            # reason as final_round.
            exhausted_steps=replan_ledger.exhausted() if replan_ledger else [],
            # Scopes a replan to the failed region + protected steps (§4.2);
            # None on the first round and any non-replan round.
            replan_focus=replan_focus,
        )
        planner_output = await build_next_plan_steps(
            planner_input=planner_input,
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-planner-{invocation}",
            invocation=invocation,
        )
        plan_status = planner_output.plan_status
        state.merge_plan_graph(planner_output.plan_graph)

        if plan_status == "blocked_needs_clarification":
            clarification_question = planner_output.clarification_question
            break

        monitor_flags = []
        replan_reason = None
        replan_focus = None  # consumed above; rebuilt below only if this round replans
        should_replan = False
        # This round's failed steps + verbatim unmet criteria, folded into a
        # scoped `replan_focus` for the next invocation (§4.2).
        round_failed_step_ids: list[str] = []
        round_unmet: list[str] = []
        steps_by_id = {step.step_id: step for step in planner_output.next_steps}

        async def _dispatch_one(step_id: str, _steps_by_id: dict[str, PlanStep] = steps_by_id) -> StateEntry:
            return await run_task_handler(
                step=_steps_by_id[step_id],
                state=state,
                role_roster=role_roster,
                tool_registry=tool_registry,
                llm_adapter=llm_adapter,
                original_user_message=original_user_message,
                user_id=user_id,
                plan_id=plan_id,
                streaming_queue=streaming_queue,
                tool_call_cache=tool_call_cache,
                unresolvable_registry=unresolvable_registry,
                reasoning_config=reasoning_config,
            )

        # Dispatch one execution layer at a time -- steps within a layer are
        # independent of each other (that's what makes them the same layer)
        # and run concurrently; each layer fully completes and gets appended
        # to `state` before the next layer starts, so a later layer's steps
        # can rely on an earlier layer's results being present. Mirrors
        # `task_handler.py::_execute_pipeline_once`'s identical layer-by-layer
        # pattern, so both nesting levels of this orchestrator share one
        # mental model instead of two.
        for layer in planner_output.plan_graph.execution_layers:
            entries = await dispatch_layer_concurrently(layer, _dispatch_one)
            for step_id, entry in zip(layer, entries):
                state.append(entry)
                step = steps_by_id[step_id]
                decision, unmet_criteria = await evaluate_step_result(
                    step, entry, llm_adapter=llm_adapter, block_id=f"{plan_id}-{step.step_id}-monitor"
                )
                if decision == "replan":
                    monitor_flags.append(f"step {step.step_id} failed")
                    replan_reason = f"step {step.step_id} failed"
                    should_replan = True
                    round_failed_step_ids.append(step.step_id)
                    if replan_ledger is not None:
                        replan_ledger.record(step.objective, replan_reason)
                if decision == "clarify":
                    # Thread the success-check's own verbatim unmet_criteria
                    # in, not just a generic phrase -- without this the
                    # re-invoked Planner only knows SOMETHING was missing,
                    # not WHAT, and tends to reissue an equivalent step that
                    # fails the identical way (see task_handler_success_check
                    # .py's SuccessCheckResult docstring).
                    if unmet_criteria:
                        detail = "; ".join(unmet_criteria)
                        monitor_flags.append(f"step {step.step_id} did not fully satisfy its success criteria: {detail}")
                        replan_reason = f"step {step.step_id} still needs: {detail}"
                    else:
                        monitor_flags.append(
                            f"step {step.step_id} partial or did not fully satisfy its success criteria"
                        )
                    round_failed_step_ids.append(step.step_id)
                    round_unmet.extend(unmet_criteria)
                    if replan_ledger is not None:
                        replan_ledger.record(step.objective, replan_reason or "unmet success criteria")
            if should_replan:
                # Let the whole in-flight layer finish (it already has, by
                # the time we get here) but never start the NEXT layer once
                # this batch needs a replan -- same semantics the old
                # sequential loop had (stop dispatching further steps in
                # this batch once a failure is detected), just at layer
                # granularity instead of per-step.
                break

        if should_replan:
            # Scope the next invocation to the failed region: fix the steps that
            # fell short, and protect everything already established so the
            # Planner repairs rather than re-derives (§4.2). Protected = the
            # succeeded entries that aren't themselves in the failed set.
            protected_step_ids = [
                entry.step_id
                for entry in state.entries
                if entry.status == "succeeded" and entry.step_id not in round_failed_step_ids
            ]
            replan_focus = ReplanFocus(
                failed_step_ids=round_failed_step_ids,
                protected_step_ids=protected_step_ids,
                unmet_criteria=round_unmet,
            )
            continue
        if plan_status == "complete":
            break

    # A genuine clarification block is the ONLY path that returns without an
    # answer. Budget exhaustion (the plan never reached "complete" but the
    # Planner never asked to clarify either) must NOT return an empty turn --
    # it falls through to compose a best-effort answer from whatever the plan
    # established, honestly reflecting what could not be determined. (A live
    # run found a turn silently exhausting the invocation budget while
    # re-resolving an ambiguous entity, returning nothing to the student.)
    if clarification_question is not None:
        return state, None, clarification_question
    if not state.entries:
        return state, None, None

    # The vision's own worked example (§7) dispatches Composition as just
    # another plan step, through the same generic path as every other role
    # -- if the Planner already ended the plan that way, its own StateEntry
    # *is* the final answer. `synthesis.compose_answer` is the safety net for
    # a plan that reached "complete" (or ran out of rounds) without ever
    # assigning a composition step.
    if state.entries[-1].role == "composition":
        return state, state.entries[-1], None

    composed = await compose_answer(
        state=state,
        user_goal=user_goal,
        composition_role=role_roster["composition"],
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-synthesis",
        streaming_queue=streaming_queue,
    )
    fallback_entry = StateEntry(
        entry_id=f"synthesis-{len(state.entries)}",
        step_id="synthesis",
        role="composition",
        status=composed.status,
        output_schema_name="composition_agent_output_v1",
        data=composed.result or {},
        certainty=composed.certainty,
        assumptions=composed.assumptions,
        warnings=composed.warnings,
        tool_audit_trail=composed.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )
    state.append(fallback_entry)
    return state, fallback_entry, None


__all__ = ["DEFAULT_MAX_PLANNER_INVOCATIONS", "run_plan_to_completion"]
