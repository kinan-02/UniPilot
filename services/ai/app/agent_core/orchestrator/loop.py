"""The Orchestrator's main loop (docs/agent/AGENT_VISION.md §3, §7, §9):
Planner -> (step-prep -> prompt_builder -> context_builder -> subagent_builder
-> subagent.run -> state.append -> Monitor) per step -> repeat, re-invoking
the Planner with the updated state, until the plan is judged complete ->
Synthesis.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.planner import build_next_plan_steps
from app.agent_core.planning.schemas import PlannerInvocationInput, RoleName
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.synthesis.synthesis import compose_answer
from app.agent_core.tools.registry import ToolRegistry

DEFAULT_MAX_PLANNER_INVOCATIONS = 5


async def run_plan_to_completion(
    *,
    user_goal: str,
    original_user_message: str,
    llm_adapter: LLMAdapter,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    plan_id: str,
    max_planner_invocations: int = DEFAULT_MAX_PLANNER_INVOCATIONS,
    sub_asks: list[str] | None = None,
    constraints: list[str] | None = None,
    open_questions: list[str] | None = None,
    implies_action_request: bool = False,
) -> tuple[PlanExecutionState, StateEntry | None]:
    """Drives one full turn: adaptive planning + per-step dispatch + Synthesis.

    Returns `(state, None)` when the plan never reached `plan_status="complete"`
    (blocked on clarification, or the invocation budget ran out) -- the caller
    must treat `None` as "no answer yet," not a crash. Otherwise returns the
    final `StateEntry` to compose the answer from (a composition-role step's
    own entry if the Planner ended the plan with one, else a synthesis
    fallback entry -- see below).
    """
    state = PlanExecutionState(plan_id=plan_id)
    monitor_flags: list[str] = []
    replan_reason: str | None = None
    plan_status = "in_progress"

    for invocation in range(1, max_planner_invocations + 1):
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
            break

        monitor_flags = []
        replan_reason = None
        should_replan = False

        for step in planner_output.next_steps:
            entry = await run_task_handler(
                step=step,
                state=state,
                role_roster=role_roster,
                tool_registry=tool_registry,
                llm_adapter=llm_adapter,
                original_user_message=original_user_message,
                plan_id=plan_id,
            )
            state.append(entry)

            decision = evaluate_step_result(step, entry)
            if decision == "replan":
                monitor_flags.append(f"step {step.step_id} failed")
                replan_reason = f"step {step.step_id} failed"
                should_replan = True
                break
            if decision == "clarify":
                monitor_flags.append(f"step {step.step_id} partial")

        if should_replan:
            continue
        if plan_status == "complete":
            break

    if plan_status != "complete":
        return state, None

    # The vision's own worked example (§7) dispatches Composition as just
    # another plan step, through the same generic path as every other role
    # -- if the Planner already ended the plan that way, its own StateEntry
    # *is* the final answer. `synthesis.compose_answer` is the safety net
    # for a plan that reached "complete" without ever assigning a
    # composition step.
    if state.entries and state.entries[-1].role == "composition":
        return state, state.entries[-1]

    composed = await compose_answer(
        state=state,
        user_goal=user_goal,
        composition_role=role_roster["composition"],
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-synthesis",
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
    return state, fallback_entry


__all__ = ["DEFAULT_MAX_PLANNER_INVOCATIONS", "run_plan_to_completion"]
