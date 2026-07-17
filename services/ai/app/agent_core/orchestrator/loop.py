"""The Orchestrator's main loop (docs/agent/AGENT_VISION.md §3, §7, §9):
Planner -> (step-prep -> prompt_builder -> context_builder -> subagent_builder
-> subagent.run -> state.append -> Monitor) per step -> repeat, re-invoking
the Planner with the updated state, until the plan is judged complete ->
Synthesis.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.orchestrator.parallel_dispatch import dispatch_layer_concurrently
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.specialist_router import route_plan
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.planner import build_next_plan_steps
from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStep, ReplanFocus
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.response_language import HEBREW, detect_message_language
from app.agent_core.synthesis.synthesis import compose_answer
from app.agent_core.turn_context import TurnContext

logger = logging.getLogger(__name__)

DEFAULT_MAX_PLANNER_INVOCATIONS = 5

_EMPTY_ANSWER_MARKER = "synthesis_produced_no_answer_text"

# Said in the student's own language, for the same reason every other answer is.
# Deliberately admits the failure rather than dressing it up: the student can act
# on "I could not determine this, ask the secretariat"; they cannot act on "".
_NO_ANSWER_MESSAGE = {
    "English": (
        "I could not determine an answer to this from your academic records and the course "
        "catalog. Please try rephrasing your question, or check with your academic advisor or "
        "the faculty secretariat."
    ),
    "Hebrew": (
        "לא הצלחתי להגיע לתשובה לשאלה זו מתוך הרשומות האקדמיות שלך ומקטלוג הקורסים. "
        "נסה לנסח את השאלה מחדש, או פנה ליועץ האקדמי או למזכירות הפקולטה."
    ),
}


def _answer_text_from(data: dict | None) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("answer_text") or "").strip()


def _answer_text(entry: StateEntry) -> str:
    return _answer_text_from(entry.data)


def _no_answer_message(original_user_message: str) -> str:
    language = detect_message_language(original_user_message)
    return _NO_ANSWER_MESSAGE[HEBREW if language == HEBREW else "English"]


async def run_plan_to_completion(
    *,
    ctx: TurnContext,
    user_goal: str,
    max_planner_invocations: int = DEFAULT_MAX_PLANNER_INVOCATIONS,
    sub_asks: list[str] | None = None,
    constraints: list[str] | None = None,
    open_questions: list[str] | None = None,
    implies_action_request: bool = False,
) -> tuple[PlanExecutionState, StateEntry | None, str | None]:
    """Drives one full turn: adaptive planning + per-step dispatch + Synthesis.

    `ctx` carries the turn's wiring (adapter, tools, roles, and the three
    per-turn registries). Everything still spelled out here is the REQUEST --
    what this turn was actually asked to do -- which stays visible at the call
    site rather than being folded into the context object.

    Returns `(state, None, clarification_question)` when the plan never
    reached `plan_status="complete"` -- the caller must treat a `None` final
    entry as "no answer yet," not a crash. `clarification_question` is the
    real question text when the plan is blocked on a genuine ambiguity, else
    `None` (e.g. the invocation budget simply ran out). Otherwise returns
    `(state, final_entry, None)`: the final `StateEntry` to compose the
    answer from (a composition-role step's own entry if the Planner ended
    the plan with one, else a synthesis fallback entry -- see below).
    """
    state = PlanExecutionState(plan_id=ctx.plan_id)
    monitor_flags: list[str] = []
    replan_reason: str | None = None
    replan_focus: ReplanFocus | None = None
    plan_status = "in_progress"
    clarification_question: str | None = None

    _max_invocations = ctx.reasoning.max_planner_invocations if ctx.reasoning else max_planner_invocations
    for invocation in range(1, _max_invocations + 1):
        # On the last available round, tell the Planner to conclude (compose or
        # clarify) rather than schedule more exploration -- otherwise a turn
        # that keeps re-trying an unresolvable/ambiguous entity simply exhausts
        # the budget and returns nothing. Carried on its own `final_round`
        # field, NOT in monitor_flags, so the council's adaptive-depth gate
        # doesn't misread a wrap-up as a replan (see planner schema).
        planner_input = PlannerInvocationInput(
            user_goal=user_goal,
            original_user_message=ctx.original_user_message,
            sub_asks=sub_asks or [],
            constraints=constraints or [],
            open_questions=open_questions or [],
            implies_action_request=implies_action_request,
            state_index=build_state_index(state.entries),
            plan_graph_so_far=state.plan_graph,
            monitor_flags=monitor_flags,
            replan_reason=replan_reason,
            unresolvable_entities=ctx.unresolvable.snapshot(),
            final_round=(invocation == _max_invocations),
            # Objectives re-attempted past the replan threshold and still
            # failing -- the Planner is told not to reschedule equivalent work
            # for these (§4.1). Kept off monitor_flags for the same council-gate
            # reason as final_round.
            exhausted_steps=ctx.replans.exhausted(),
            # Scopes a replan to the failed region + protected steps (§4.2);
            # None on the first round and any non-replan round.
            replan_focus=replan_focus,
        )
        planner_output = await build_next_plan_steps(
            planner_input=planner_input,
            llm_adapter=ctx.llm,
            block_id=ctx.block_id("planner", str(invocation)),
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

        # Route this whole batch in ONE call, before any layer runs, instead of
        # paying a blocking router call per step -- on a live run (2026-07-15)
        # 24 of 25 routes were a single specialist label the step's own
        # objective already determined, and each one stalled its step's layer.
        #
        # Best-effort by construction: `route_plan` returns {} on any failure,
        # and `run_task_handler` re-routes any step whose dependencies came back
        # unclean (see `_dependencies_are_clean`), so this can only remove calls
        # -- it can never make a step run unrouted or wrongly routed.
        precomputed_routes = await route_plan(
            steps=list(planner_output.next_steps),
            llm_adapter=ctx.llm,
            block_id=ctx.block_id("plan-router", str(invocation)),
            role_roster=ctx.roles,
        )

        async def _dispatch_one(step_id: str, _steps_by_id: dict[str, PlanStep] = steps_by_id) -> StateEntry:
            return await run_task_handler(
                step=_steps_by_id[step_id],
                state=state,
                ctx=ctx,
                precomputed_route=precomputed_routes.get(step_id),
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
                    step, entry, llm_adapter=ctx.llm, block_id=ctx.block_id(step.step_id, "monitor")
                )
                if decision == "replan":
                    monitor_flags.append(f"step {step.step_id} failed")
                    replan_reason = f"step {step.step_id} failed"
                    should_replan = True
                    round_failed_step_ids.append(step.step_id)
                    ctx.replans.record(step.objective, replan_reason)
                if decision == "clarify":
                    # A step that fell short is a replan, exactly as a failed
                    # one is -- this branch used to collect the flags and the
                    # failed step id and then NOT ask for the replan, so on any
                    # round the Planner had already called "complete" the loop
                    # broke below and dropped everything gathered here. That is
                    # the missing replan the comment further down records.
                    should_replan = True
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
                    ctx.replans.record(step.objective, replan_reason or "unmet success criteria")
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
    #
    # ...but only if it actually SAID something. A composition entry with no
    # answer_text is not an answer, and returning it hands the student a blank
    # reply.
    #
    # CAUGHT LIVE (2026-07-16, ise_correctness `offering_pattern`): the
    # composition step returned `partial` with `data={}` via task_handler's
    # empty-dependency-context guard -- whose own comment says it fails partial
    # "so the Monitor replans, rather than emitting a confident wrong answer".
    # No replan came. The plan was already complete, this line accepted the empty
    # entry, and the student got "". The guard was right to refuse to compose
    # from nothing; nothing downstream honoured it.
    #
    # Falling through to `compose_answer` is a real recovery rather than a
    # cosmetic one: it composes over the WHOLE state, and in that run a sibling
    # retrieval step had succeeded with exactly the offering data the answer
    # needed. The empty entry stays in state -- it is a true record of what that
    # step did.
    if state.entries[-1].role == "composition" and _answer_text(state.entries[-1]):
        return state, state.entries[-1], None

    composed = await compose_answer(
        state=state,
        user_goal=user_goal,
        composition_role=ctx.roles["composition"],
        tool_registry=ctx.tools,
        llm_adapter=ctx.llm,
        block_id=ctx.block_id("synthesis"),
        original_user_message=ctx.original_user_message,
        streaming_queue=ctx.stream,
    )
    # Last line of defence. If even synthesis produced nothing, say so in words
    # rather than shipping an empty string: a blank reply tells the student
    # nothing, hides that anything went wrong, and (measured live) sails through
    # any gate that only checks a final entry exists. An honest "I could not
    # determine this" is a worse answer than a real one and a far better one
    # than silence.
    data = composed.result or {}
    warnings = list(composed.warnings)
    if not _answer_text_from(data):
        logger.warning("synthesis_produced_no_answer_text plan_id=%s status=%s", ctx.plan_id, composed.status)
        data = {**data, "answer_text": _no_answer_message(ctx.original_user_message)}
        warnings.append(_EMPTY_ANSWER_MARKER)

    fallback_entry = StateEntry(
        entry_id=f"synthesis-{len(state.entries)}",
        step_id="synthesis",
        role="composition",
        status=composed.status,
        output_schema_name="composition_agent_output_v1",
        data=data,
        certainty=composed.certainty,
        assumptions=composed.assumptions,
        warnings=warnings,
        tool_audit_trail=composed.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )
    state.append(fallback_entry)
    return state, fallback_entry, None


__all__ = ["DEFAULT_MAX_PLANNER_INVOCATIONS", "run_plan_to_completion"]
