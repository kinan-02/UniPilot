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
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.planner import build_next_plan_steps
from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStep, RoleName
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
    plan_status = "in_progress"
    clarification_question: str | None = None

    _max_invocations = reasoning_config.max_planner_invocations if reasoning_config else max_planner_invocations
    for invocation in range(1, _max_invocations + 1):
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
        )
        planner_output = await build_next_plan_steps(
            planner_input=planner_input,
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-planner-{invocation}",
            invocation=invocation,
            thinking_enabled=reasoning_config.planner_thinking_enabled if reasoning_config else None,
            reasoning_effort=reasoning_config.planner_reasoning_effort if reasoning_config else None,
            timeout=reasoning_config.planner_timeout if reasoning_config else None,
        )
        plan_status = planner_output.plan_status
        state.merge_plan_graph(planner_output.plan_graph)

        if plan_status == "blocked_needs_clarification":
            clarification_question = planner_output.clarification_question
            break

        monitor_flags = []
        replan_reason = None
        should_replan = False
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
        # `task_handler.py::_run_nested_subplan`'s identical layer-by-layer
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
            if should_replan:
                # Let the whole in-flight layer finish (it already has, by
                # the time we get here) but never start the NEXT layer once
                # this batch needs a replan -- same semantics the old
                # sequential loop had (stop dispatching further steps in
                # this batch once a failure is detected), just at layer
                # granularity instead of per-step.
                break

        if should_replan:
            continue
        if plan_status == "complete":
            break

    if plan_status != "complete":
        return state, None, clarification_question

    # The vision's own worked example (§7) dispatches Composition as just
    # another plan step, through the same generic path as every other role
    # -- if the Planner already ended the plan that way, its own StateEntry
    # *is* the final answer. `synthesis.compose_answer` is the safety net
    # for a plan that reached "complete" without ever assigning a
    # composition step.
    if state.entries and state.entries[-1].role == "composition":
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
