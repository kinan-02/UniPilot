"""The task handler (docs/agent/AGENT_VISION.md §7, task-handler follow-up):
absorbs the case where a single `PlanStep` is itself too complex for one
specialist-subagent call.

`run_task_handler` is the ONE entry point `orchestrator/loop.py` calls per
top-level step, replacing the old inline `_stopgap_role_for_step` +
`run_step_prep` + `build_subagent_context_package` + `run_subagent` +
`StateEntry`-construction block. It cheaply classifies the step
(`task_handler_classifier.classify_step`): atomic steps get dispatched
directly to one specialist, same as today, just with a real role decision
instead of keyword-matching; non-atomic steps (or an atomic dispatch whose
result fails its own `success_criteria` check -- a second-line safety net,
not the primary mechanism) get resolved via a private, bounded sub-plan.

Depth-cap invariant: `run_task_handler` is the ONLY function that runs the
classifier to decide *whether to recurse*, and the ONLY function that ever
invokes the nested Planner as part of that decision. Nothing it calls,
directly or transitively, calls it again -- there is no second call site in
this module for its own name, enforced structurally, not by a runtime
counter (see `tests/agent_core/test_orchestrator_task_handler.py`'s
`inspect.getsource` regression guard).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.agent_core.orchestrator.context_builder import build_subagent_context_package
from app.agent_core.orchestrator.parallel_dispatch import dispatch_layer_concurrently
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.task_handler_classify_and_prep import classify_and_prep_step
from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.planner import NESTED_PLANNER_V1, build_next_plan_steps
from app.agent_core.reasoning_effort import TurnReasoningConfig
from app.agent_core.reasoning_blocks.schemas import LLMCallParameters
from app.agent_core.planning.schemas import PlannerInvocationInput, PlanStep, RoleName
from app.agent_core.planning.state import (
    CertaintyTag,
    NestedExecutionTrace,
    NestedStepTrace,
    PlanExecutionState,
    StateEntry,
)
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.calculation_validation_block import run_calculation_validation_subagent
from app.agent_core.subagents.composition_block import run_composition_subagent
from app.agent_core.subagents.interpretation_block import run_interpretation_subagent
from app.agent_core.subagents.retrieval_block import run_retrieval_subagent
from app.agent_core.subagents.simulation_planning_block import run_simulation_planning_subagent
from app.agent_core.subagents.run import run_subagent
from app.agent_core.subagents.schemas import SubagentResult
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry

DEFAULT_MAX_TASK_HANDLER_ROUNDS = 3
_ROUND_BUDGET_EXHAUSTED_WARNING = "task_handler_round_budget_exhausted"


async def run_task_handler(
    *,
    step: PlanStep,
    state: PlanExecutionState,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    original_user_message: str,
    user_id: str,
    plan_id: str,
    max_rounds: int = DEFAULT_MAX_TASK_HANDLER_ROUNDS,
    streaming_queue: asyncio.Queue[str] | None = None,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    reasoning_config: TurnReasoningConfig | None = None,
) -> StateEntry:
    """Never appends to `state` itself -- the caller still owns
    `state.append(entry)`, unchanged from today's `loop.py` behavior."""
    classifier_output, step_prep_output = await classify_and_prep_step(
        step=step,
        dependency_context=build_state_index(state.slice(step.depends_on)),
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-{step.step_id}-classify_and_prep",
        user_id=user_id,
    )

    fallback_reason: str | None = None
    if classifier_output.atomic and classifier_output.role_if_atomic is not None:
        role_name = classifier_output.role_if_atomic
        result = await _dispatch_single_specialist(
            step=step,
            step_prep_output=step_prep_output,
            role=role_roster[role_name],
            state=state,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-{step.step_id}",
            user_id=user_id,
            streaming_queue=streaming_queue,
            tool_call_cache=tool_call_cache,
            unresolvable_registry=unresolvable_registry,
            reasoning_config=reasoning_config,
        )
        criteria_met = result.status == "succeeded" and await check_success_criteria(
            step=step,
            result=result,
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-{step.step_id}-success-check",
        )
        if criteria_met:
            return _entry_from_atomic_result(step=step, role=role_name, result=result, state=state)
        fallback_reason = "fast_path_inadequate"
    else:
        fallback_reason = "classified_non_atomic"

    private_state, clarification_question, rounds_used, rounds_exhausted = await _run_nested_subplan(
        step=step,
        parent_state=state,
        role_roster=role_roster,
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        original_user_message=original_user_message,
        user_id=user_id,
        plan_id=plan_id,
        max_rounds=max_rounds,
        tool_call_cache=tool_call_cache,
        unresolvable_registry=unresolvable_registry,
        reasoning_config=reasoning_config,
    )
    return _entry_from_nested_subplan(
        step=step,
        state=state,
        private_state=private_state,
        clarification_question=clarification_question,
        rounds_used=rounds_used,
        rounds_exhausted=rounds_exhausted,
        fallback_reason=fallback_reason,
    )


async def _dispatch_single_specialist(
    *,
    step: PlanStep,
    step_prep_output: StepPrepOutput,
    role: RoleDefinition,
    state: PlanExecutionState,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    user_id: str,
    streaming_queue: asyncio.Queue[str] | None = None,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    reasoning_config: TurnReasoningConfig | None = None,
) -> SubagentResult:
    """The existing context_builder -> run_subagent chain,
    wrapped as one non-recursive helper -- used by BOTH the atomic fast path
    above and every nested sub-step below. Generic over whichever
    `PlanExecutionState` it's given (the shared top-level `state`, or a
    task handler's own private one)."""
    context_package = build_subagent_context_package(step_prep=step_prep_output, role=role, state=state)
    if role.name == "calculation_validation":
        return await run_calculation_validation_subagent(
            context_package=context_package,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=block_id,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout) if reasoning_config else None,
        )
    if role.name == "retrieval":
        return await run_retrieval_subagent(
            context_package=context_package,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=block_id,
            tool_call_cache=tool_call_cache,
            unresolvable_registry=unresolvable_registry,
            llm_call_params=LLMCallParameters(timeout=reasoning_config.static_subagent_timeout) if reasoning_config else None,
        )
    if role.name == "interpretation":
        return await run_interpretation_subagent(
            context_package=context_package,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=block_id,
            tool_call_cache=tool_call_cache,
            unresolvable_registry=unresolvable_registry,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout) if reasoning_config else None,
        )
    if role.name == "simulation_planning":
        return await run_simulation_planning_subagent(
            context_package=context_package,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=block_id,
            tool_call_cache=tool_call_cache,
            unresolvable_registry=unresolvable_registry,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout) if reasoning_config else None,
        )
    if role.name == "composition":
        return await run_composition_subagent(
            context_package=context_package,
            llm_adapter=llm_adapter,
            block_id=block_id,
            streaming_queue=streaming_queue,
            llm_call_params=LLMCallParameters(timeout=reasoning_config.static_subagent_timeout) if reasoning_config else None,
        )
    return await run_subagent(
        role=role,
        context_package=context_package,
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=block_id,
    )


def _entry_from_atomic_result(
    *, step: PlanStep, role: RoleName, result: SubagentResult, state: PlanExecutionState
) -> StateEntry:
    """Atomic path: certainty is exactly whatever the one specialist
    returned, unchanged -- no nested_trace."""
    return StateEntry(
        entry_id=f"{step.step_id}-{len(state.entries)}",
        step_id=step.step_id,
        role=role,
        status=result.status,
        output_schema_name="generic_step_output_v1",
        data=result.result or {},
        certainty=result.certainty,
        assumptions=result.assumptions,
        warnings=result.warnings,
        tool_audit_trail=result.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )


async def _run_nested_subplan(
    *,
    step: PlanStep,
    parent_state: PlanExecutionState,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    original_user_message: str,
    user_id: str,
    plan_id: str,
    max_rounds: int,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    reasoning_config: TurnReasoningConfig | None = None,
) -> tuple[PlanExecutionState, str | None, int, bool]:
    """The task handler's own private mini-orchestrator: mirrors
    `orchestrator/loop.py::run_plan_to_completion`'s own invoke-repeatedly
    rhythm, scoped privately. Never spawns a second `run_task_handler` /
    classifier-decides-recursion instance for its own sub-steps -- a
    sub-step that itself comes back non-atomic (or fails its own
    success-criteria check) becomes a failed `StateEntry`, which feeds
    `monitor_flags`/`replan_reason` into the NEXT round of this SAME
    already-active nested Planner instead."""
    private_state = PlanExecutionState(plan_id=f"{parent_state.plan_id}:{step.step_id}")
    # Pre-seed known_global_ids for rewrite_step_ids: a nested sub-step may
    # legitimately depend on one of the PARENT step's own dependencies (it's
    # shown those ids via state_index below, and the Planner's own existing
    # instructions tell it to reference an already-known id directly when
    # relevant). Without this, a brand-new private plan's
    # plan_graph_so_far.forward starts with none of the parent's ids, and
    # rewrite.py would silently strip such a reference as a "dangling"
    # dependency.
    private_state.plan_graph.forward.update({dep_id: [] for dep_id in step.depends_on})
    # The graph-shape pre-seed above only stops rewrite.py from stripping the
    # reference as dangling -- it does NOT make the parent's actual data
    # available. Without copying the real entries too, a nested sub-step
    # whose `context_requirements` names one of these parent dependency ids
    # gets back an EMPTY `state.slice(...)` (the data lives in `parent_state.
    # entries`, never in `private_state.entries`), so `context_builder.py`
    # hands it an empty `dependency_state` and e.g. `calculation_validation`
    # fails with "ref '<name>' not found in facts (available: [])" no matter
    # how many rounds it gets -- a structurally impossible-to-satisfy retry,
    # not a genuine transient failure.
    for parent_entry in parent_state.slice(step.depends_on):
        private_state.append(parent_entry)

    clarification_question: str | None = None
    rounds_used = 0
    round_monitor_flags: list[str] = []
    round_replan_reason: str | None = None

    for invocation in range(1, max_rounds + 1):
        rounds_used = invocation
        planner_input = _nested_planner_input(
            step=step,
            parent_state=parent_state,
            private_state=private_state,
            original_user_message=original_user_message,
            monitor_flags=round_monitor_flags,
            replan_reason=round_replan_reason,
            unresolvable_registry=unresolvable_registry,
        )
        planner_output = await build_next_plan_steps(
            planner_input=planner_input,
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-{step.step_id}-nested-planner-{invocation}",
            invocation=invocation,
            prompt_contract_name=NESTED_PLANNER_V1,
        )
        private_state.merge_plan_graph(planner_output.plan_graph)

        if planner_output.plan_status == "blocked_needs_clarification":
            return private_state, planner_output.clarification_question, rounds_used, False

        steps_by_id = {sub_step.step_id: sub_step for sub_step in planner_output.next_steps}

        async def _dispatch_one(step_id: str, _steps_by_id: dict[str, PlanStep] = steps_by_id) -> StateEntry:
            return await _dispatch_nested_sub_step(
                sub_step=_steps_by_id[step_id],
                private_state=private_state,
                role_roster=role_roster,
                tool_registry=tool_registry,
                llm_adapter=llm_adapter,
                plan_id=plan_id,
                step=step,
                user_id=user_id,
                tool_call_cache=tool_call_cache,
                unresolvable_registry=unresolvable_registry,
                reasoning_config=reasoning_config,
            )

        round_monitor_flags = []
        round_replan_reason = None
        replan_needed = False

        for layer in planner_output.plan_graph.execution_layers:
            entries = await dispatch_layer_concurrently(layer, _dispatch_one)
            for entry in entries:
                private_state.append(entry)
                if entry.status != "succeeded":
                    replan_needed = True
                    round_monitor_flags.append(
                        f"step {entry.step_id} could not be completed atomically or failed its success-criteria check"
                    )
                    round_replan_reason = f"step {entry.step_id} needs finer-grained decomposition"

        if replan_needed:
            continue
        if planner_output.plan_status == "complete":
            return private_state, None, rounds_used, False

    return private_state, None, rounds_used, True  # rounds exhausted


async def _dispatch_nested_sub_step(
    *,
    sub_step: PlanStep,
    private_state: PlanExecutionState,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    plan_id: str,
    step: PlanStep,
    user_id: str,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    reasoning_config: TurnReasoningConfig | None = None,
) -> StateEntry:
    """One sub-step of the private sub-plan. Calls the classifier for ROLE
    ASSIGNMENT ONLY -- it does not re-decide whether to recurse. If this
    sub-step also comes back non-atomic (or fails its own success-criteria
    check), that's surfaced as a failed/partial `StateEntry` so
    `_run_nested_subplan`'s own `replan_needed` flag triggers ANOTHER round
    of the SAME already-active nested Planner, never a second task-handler
    instance."""
    classifier_output, step_prep_output = await classify_and_prep_step(
        step=sub_step,
        dependency_context=build_state_index(private_state.entries),
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-{step.step_id}-{sub_step.step_id}-classify_and_prep",
        user_id=user_id,
    )
    if not (classifier_output.atomic and classifier_output.role_if_atomic is not None):
        return _failed_entry(
            sub_step=sub_step, private_state=private_state, warning="nested_sub_step_classified_non_atomic"
        )

    role_name = classifier_output.role_if_atomic
    result = await _dispatch_single_specialist(
        step=sub_step,
        step_prep_output=step_prep_output,
        role=role_roster[role_name],
        state=private_state,
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-{step.step_id}-{sub_step.step_id}",
        user_id=user_id,
        tool_call_cache=tool_call_cache,
        unresolvable_registry=unresolvable_registry,
        reasoning_config=reasoning_config,
    )
    criteria_met = result.status == "succeeded" and await check_success_criteria(
        step=sub_step,
        result=result,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-{step.step_id}-{sub_step.step_id}-success-check",
    )
    status = result.status if criteria_met else "partial"
    warnings = result.warnings if criteria_met else [*result.warnings, "nested_sub_step_success_criteria_not_met"]
    return StateEntry(
        entry_id=f"{sub_step.step_id}-{len(private_state.entries)}",
        step_id=sub_step.step_id,
        role=role_name,
        status=status,
        output_schema_name="generic_step_output_v1",
        data=result.result or {},
        certainty=result.certainty,
        assumptions=result.assumptions,
        warnings=warnings,
        tool_audit_trail=result.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )


def _failed_entry(*, sub_step: PlanStep, private_state: PlanExecutionState, warning: str) -> StateEntry:
    return StateEntry(
        entry_id=f"{sub_step.step_id}-{len(private_state.entries)}",
        step_id=sub_step.step_id,
        role="retrieval",
        status="failed",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="llm_interpretation", confidence=0.0),
        warnings=[warning],
        produced_at=datetime.now(timezone.utc),
    )


def _nested_planner_input(
    *,
    step: PlanStep,
    parent_state: PlanExecutionState,
    private_state: PlanExecutionState,
    original_user_message: str,
    monitor_flags: list[str],
    replan_reason: str | None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
) -> PlannerInvocationInput:
    dependency_entries = parent_state.slice(step.depends_on)
    return PlannerInvocationInput(
        user_goal=step.objective,
        original_user_message=original_user_message,
        sub_asks=[],
        # Constraints stay empty: the top-level Planner already threads any
        # constraint bearing on this step into the step's own `objective`
        # text at plan-creation time (its own prompt contract's explicit
        # instruction) -- no separate pass-through is needed here.
        constraints=[],
        open_questions=list(step.assumptions_to_verify),
        implies_action_request=False,
        state_index=[*build_state_index(dependency_entries), *build_state_index(private_state.entries)],
        plan_graph_so_far=private_state.plan_graph,
        monitor_flags=monitor_flags,
        replan_reason=replan_reason,
        unresolvable_entities=unresolvable_registry.snapshot() if unresolvable_registry else [],
    )


def _entry_from_nested_subplan(
    *,
    step: PlanStep,
    state: PlanExecutionState,
    private_state: PlanExecutionState,
    clarification_question: str | None,
    rounds_used: int,
    rounds_exhausted: bool,
    fallback_reason: str | None,
) -> StateEntry:
    """Translates the private sub-plan's outcome into the ONE `StateEntry`
    the parent plan sees. `blocked_needs_clarification` is never surfaced to
    the user directly here (the task handler has no interrupt authority) --
    its exact question text is preserved verbatim in `warnings` so whichever
    component DOES have that authority can act on it. Certainty aggregates
    via the same min-confidence-across-facts convention used elsewhere in
    this codebase (`compose_answer.py`, `search_over_state.py`)."""
    warnings: list[str] = [fallback_reason] if fallback_reason else []
    succeeded_entries = [entry for entry in private_state.entries if entry.status == "succeeded"]

    if clarification_question:
        warnings.append(f"nested_planner_blocked_needs_clarification: {clarification_question}")
        status = "partial"
    elif rounds_exhausted:
        warnings.append(_ROUND_BUDGET_EXHAUSTED_WARNING)
        status = "partial" if succeeded_entries else "failed"
    elif private_state.entries and len(succeeded_entries) == len(private_state.entries):
        status = "succeeded"
    else:
        status = "partial" if succeeded_entries else "failed"

    if succeeded_entries:
        weakest = min(succeeded_entries, key=lambda entry: entry.certainty.confidence)
        certainty = CertaintyTag(basis=weakest.certainty.basis, confidence=weakest.certainty.confidence)
    else:
        certainty = CertaintyTag(basis="llm_interpretation", confidence=0.0)

    # Resolved (not left open): loop.py's own composition short-circuit
    # checks `state.entries[-1].role == "composition"`, so this isn't
    # cosmetic. The last SUCCESSFUL entry's role (in the private plan's own
    # append order) correctly propagates "composition" when the sub-plan
    # genuinely ended with a composition-shaped step; falls back to
    # "retrieval" only when nothing succeeded at all.
    role: RoleName = succeeded_entries[-1].role if succeeded_entries else "retrieval"

    if succeeded_entries and role == "composition":
        # `routes/advise.py`'s final-answer extraction and loop.py's own
        # composition short-circuit both do a flat `data.get("answer_text")`
        # on any StateEntry whose role is "composition" -- wrapping it under
        # `sub_results` like every other role silently produces a blank
        # final answer even though the agent composed a correct one
        # internally (found via a live-eval run: the composed answer was
        # buried at data["sub_results"]["1a"]["answer_text"]).
        data = succeeded_entries[-1].data
    else:
        data = {"sub_results": {entry.step_id: entry.data for entry in succeeded_entries}}
    all_warnings = [*warnings, *(w for entry in private_state.entries for w in entry.warnings)]
    all_assumptions = [a for entry in private_state.entries for a in entry.assumptions]
    all_tool_audit = [record for entry in private_state.entries for record in entry.tool_audit_trail]

    nested_trace = NestedExecutionTrace(
        private_plan_id=private_state.plan_id,
        rounds_used=rounds_used,
        rounds_exhausted=rounds_exhausted,
        entries=[
            NestedStepTrace(
                entry_id=entry.entry_id,
                step_id=entry.step_id,
                role=entry.role,
                status=entry.status,
                certainty=entry.certainty,
                warnings=entry.warnings,
            )
            for entry in private_state.entries
        ],
        tool_audit_trail=all_tool_audit,
    )

    return StateEntry(
        entry_id=f"{step.step_id}-{len(state.entries)}",
        step_id=step.step_id,
        role=role,
        status=status,
        output_schema_name="generic_step_output_v1",
        data=data,
        certainty=certainty,
        assumptions=all_assumptions,
        warnings=all_warnings,
        tool_audit_trail=all_tool_audit,
        nested_trace=nested_trace,
        produced_at=datetime.now(timezone.utc),
    )


__all__ = ["DEFAULT_MAX_TASK_HANDLER_ROUNDS", "run_task_handler"]
