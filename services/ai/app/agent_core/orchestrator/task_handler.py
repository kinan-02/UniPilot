"""The task handler (docs/agent/AGENT_VISION.md §7;
docs/planning/SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md): a mini-orchestrator of
specialists, not a doer. It never uses tools itself -- the specialists own the
tools. Its job is to decide WHICH specialist type(s) execute a step and how
their outputs chain, then oversee that execution.

`run_task_handler` is the ONE entry point `orchestrator/loop.py` calls per
top-level step. It routes the step to a specialist PIPELINE via the Specialist
Router (`specialist_router.route_step`): "atomic vs complex" is a cardinality
question about specialist TYPES, so a one-specialist step is a length-1
pipeline (the atomic fast path) and a multi-specialist step is a pipeline with
data handoff between its sub-steps. The pipeline runs ONCE; a step that falls
short returns partial/failed and the outer Monitor replans one level up (it
sees the whole plan and has the criteria critic). There is deliberately no
per-step repair/re-route loop -- a live measurement showed one thrashing (8
steps -> 18 routes) because a failing atomic step just re-produced the same
single specialist.

Depth-cap invariant: `run_task_handler` is the ONLY function that runs the
router to decide a step's pipeline, and nothing it calls re-enters it -- there
is no second call site for its own name (enforced structurally; see
`tests/agent_core/test_orchestrator_task_handler.py`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.orchestrator.context_builder import build_subagent_context_package
from app.agent_core.orchestrator.parallel_dispatch import dispatch_layer_concurrently
from app.agent_core.orchestrator.specialist_router import RoutedSubStep, route_step
from app.agent_core.orchestrator.state_index import build_state_index
from app.agent_core.orchestrator.task_handler_success_check import check_success_criteria
from app.agent_core.planning.rewrite import compute_plan_graph
from app.agent_core.reasoning_blocks.schemas import LLMCallParameters
from app.agent_core.planning.schemas import PlanStep, RoleName
from app.agent_core.turn_context import TurnContext
from app.agent_core.planning.state import (
    CertaintyTag,
    NestedExecutionTrace,
    NestedStepTrace,
    PlanExecutionState,
    StateEntry,
)
from app.agent_core.roles.schemas import RoleDefinition


def _dependencies_are_clean(dependency_entries: list[StateEntry]) -> bool:
    """True when every result this step builds on came back `succeeded`.

    The gate on reusing a plan-time route: only a dependency that did something
    UNEXPECTED can make a route computed from the step's objective wrong, and
    only then is re-routing (with the real results in hand) worth its call.
    A step with no dependencies is trivially clean -- there is nothing whose
    outcome could have changed its routing.
    """
    return all(entry.status == "succeeded" for entry in dependency_entries)
from app.agent_core.response_language import response_language_directive
from app.agent_core.subagents.calculation_validation_block import run_calculation_validation_subagent
from app.agent_core.subagents.composition_block import run_composition_subagent
from app.agent_core.subagents.interpretation_block import run_interpretation_subagent
from app.agent_core.subagents.retrieval_block import run_retrieval_subagent
from app.agent_core.subagents.simulation_planning_block import run_simulation_planning_subagent
from app.agent_core.subagents.run import run_subagent
from app.agent_core.subagents.schemas import (
    ReasoningParamsOverride,
    StepInstructionFields,
    StepPrepOutput,
    SubagentResult,
)

_PIPELINE_INCOMPLETE_WARNING = "task_handler_pipeline_incomplete"
_SUB_STEP_UNMET_MARKER = "pipeline_sub_step_success_criteria_not_met"
_ATOMIC_UNMET_MARKER = "atomic_success_criteria_not_met"
_COMPOSITION_EMPTY_CONTEXT_MARKER = "composition_empty_dependency_context"


def _user_id_instruction(user_id: str) -> str:
    return (
        f"The current student's own user_id (for get_entity with entity_type="
        f"'student_profile'/'completed_courses'/'semester_plan') is: {user_id}"
    )


async def run_task_handler(
    *,
    step: PlanStep,
    state: PlanExecutionState,
    ctx: TurnContext,
    precomputed_route: list[RoutedSubStep] | None = None,
) -> StateEntry:
    """Routes the step to a specialist pipeline and executes it ONCE. It never
    re-routes/repairs locally: a live measurement showed a per-step repair loop
    thrashing (8 steps -> 18 routes) because a failing atomic step just
    re-produced the same single specialist. Recovery belongs to the Monitor,
    which sees the whole plan and can replan (with the criteria critic to relax
    an over-strict criterion) -- so a step that falls short returns
    partial/failed here and the Monitor handles it one level up.

    Never appends to `state` itself -- the caller still owns
    `state.append(entry)`."""
    dependency_entries = state.slice(step.depends_on)
    # A route precomputed for the whole plan (specialist_router.route_plan) is
    # used ONLY while this step's dependencies came back clean.
    #
    # The one thing per-step routing knows that a plan-time batch cannot is what
    # the dependencies ACTUALLY produced -- and that only changes the route when
    # they produced something unexpected. Measured live (2026-07-15): 24 of 25
    # routes were a single specialist label that the step's own objective already
    # determined; the sole route that used dependency results was reacting to a
    # failed `degreeId` lookup. So we re-route exactly there, and skip the call
    # -- and its blocking hop before every step -- everywhere else.
    if precomputed_route and _dependencies_are_clean(dependency_entries):
        pipeline = list(precomputed_route)
    else:
        route = await route_step(
            step=step,
            dependency_context=build_state_index(dependency_entries),
            llm_adapter=ctx.llm,
            block_id=ctx.block_id(step.step_id, "router"),
            user_id=ctx.user_id,
            role_roster=ctx.roles,
        )
        pipeline = route.pipeline

    # Atomic route: one specialist, verified against THIS step's own
    # success_criteria (no nested_trace, so the Monitor skips the outer
    # re-check). A failed check returns a partial/failed atomic entry rather
    # than re-routing the identical single specialist.
    if len(pipeline) == 1:  # atomic: one specialist owns the whole step
        sub = pipeline[0]
        result = await _dispatch_single_specialist(
            step=step,
            step_prep_output=_sub_step_prep(
                sub,
                user_id=ctx.user_id,
                context_requirements=_resolve_sub_step_context_requirements(sub=sub, state=state, step=step),
                original_user_message=ctx.original_user_message,
            ),
            role=ctx.roles[sub.specialist],
            state=state,
            ctx=ctx,
            block_id=ctx.block_id(step.step_id),
        )
        status = result.status
        warnings = list(result.warnings)
        if result.status == "succeeded":
            criteria_met, unmet = await check_success_criteria(
                step=step,
                result=result,
                llm_adapter=ctx.llm,
                block_id=ctx.block_id(step.step_id, "success-check"),
            )
            if not criteria_met:
                status = "partial"
                warnings = [*warnings, _ATOMIC_UNMET_MARKER, *unmet]
        return _entry_from_atomic_result(
            step=step, role=sub.specialist, result=result, state=state, status=status, warnings=warnings
        )

    # Multi-specialist route: execute the pipeline once (layer by layer, with
    # data handoff between sub-steps). A sub-step that falls short yields a
    # partial/failed aggregate for the Monitor to replan.
    private_state = _new_private_state(step=step, parent_state=state)
    pipeline_succeeded = await _execute_pipeline_once(
        step=step,
        pipeline=list(pipeline),
        private_state=private_state,
        ctx=ctx,
    )
    return _entry_from_pipeline(
        step=step,
        state=state,
        private_state=private_state,
        pipeline_succeeded=pipeline_succeeded,
        fallback_reason="routed_multi_specialist_pipeline",
    )


async def _dispatch_single_specialist(
    *,
    step: PlanStep,
    step_prep_output: StepPrepOutput,
    role: RoleDefinition,
    state: PlanExecutionState,
    ctx: TurnContext,
    block_id: str,
) -> SubagentResult:
    """The context_builder -> run_subagent chain, wrapped as one non-recursive
    helper -- used by BOTH the atomic fast path and every pipeline sub-step.
    Generic over whichever `PlanExecutionState` it's given (the shared
    top-level `state`, or a task handler's own private one).

    This is the dispatch boundary: `ctx` stops here and each specialist is
    handed only what it actually uses. See `turn_context.TurnContext` for why
    the leaves keep their narrow signatures instead of taking the whole turn."""
    context_package = build_subagent_context_package(step_prep=step_prep_output, role=role, state=state)
    # Safety net: a composition specialist has zero tool access -- it works ONLY
    # from the upstream results it is handed. If dependency resolution yielded
    # nothing (a mis-wired dependency id that survived even the parent-fallback,
    # or a genuinely dependency-less composition step), composing anyway means
    # fabricating from thin air. Fail loud/partial instead so the Monitor
    # replans, rather than emitting a confident wrong answer.
    if role.name == "composition" and not context_package.dependency_state:
        return SubagentResult(
            status="partial",
            result={},
            certainty=CertaintyTag(basis="llm_interpretation", confidence=0.0),
            warnings=[_COMPOSITION_EMPTY_CONTEXT_MARKER],
        )
    reasoning_config = ctx.reasoning
    if role.name == "calculation_validation":
        return await run_calculation_validation_subagent(
            context_package=context_package,
            tool_registry=ctx.tools,
            llm_adapter=ctx.llm,
            block_id=block_id,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout, max_retries=reasoning_config.subagent_max_retries) if reasoning_config else None,
        )
    if role.name == "retrieval":
        return await run_retrieval_subagent(
            context_package=context_package,
            tool_registry=ctx.tools,
            llm_adapter=ctx.llm,
            block_id=block_id,
            tool_call_cache=ctx.cache,
            unresolvable_registry=ctx.unresolvable,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.static_subagent_thinking_enabled, reasoning_effort=reasoning_config.static_subagent_reasoning_effort, timeout=reasoning_config.static_subagent_timeout, max_retries=reasoning_config.static_subagent_max_retries) if reasoning_config else None,
        )
    if role.name == "interpretation":
        return await run_interpretation_subagent(
            context_package=context_package,
            tool_registry=ctx.tools,
            llm_adapter=ctx.llm,
            block_id=block_id,
            tool_call_cache=ctx.cache,
            unresolvable_registry=ctx.unresolvable,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout, max_retries=reasoning_config.subagent_max_retries) if reasoning_config else None,
        )
    if role.name == "simulation_planning":
        return await run_simulation_planning_subagent(
            context_package=context_package,
            tool_registry=ctx.tools,
            llm_adapter=ctx.llm,
            block_id=block_id,
            tool_call_cache=ctx.cache,
            unresolvable_registry=ctx.unresolvable,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.subagent_thinking_enabled, reasoning_effort=reasoning_config.subagent_reasoning_effort, timeout=reasoning_config.subagent_timeout, max_retries=reasoning_config.subagent_max_retries) if reasoning_config else None,
        )
    if role.name == "composition":
        return await run_composition_subagent(
            context_package=context_package,
            llm_adapter=ctx.llm,
            block_id=block_id,
            streaming_queue=ctx.stream,
            llm_call_params=LLMCallParameters(thinking_enabled=reasoning_config.static_subagent_thinking_enabled, reasoning_effort=reasoning_config.static_subagent_reasoning_effort, timeout=reasoning_config.static_subagent_timeout, max_retries=reasoning_config.static_subagent_max_retries) if reasoning_config else None,
        )
    return await run_subagent(
        role=role,
        context_package=context_package,
        tool_registry=ctx.tools,
        llm_adapter=ctx.llm,
        block_id=block_id,
    )


def _sub_step_plan_step(sub: RoutedSubStep) -> PlanStep:
    """A pipeline sub-step as a `PlanStep`, only so `compute_plan_graph` can
    layer siblings and `check_success_criteria` can verify it. `depends_on`
    entries that name a sibling gate layering; entries that name a parent
    dependency are ignored for layering (that data is already present) but
    still reach the specialist via context_requirements."""
    return PlanStep(
        step_id=sub.sub_step_id,
        objective=sub.objective,
        depends_on=list(sub.depends_on),
        success_criteria=list(sub.success_criteria),
        assumptions_to_verify=[],
    )


def _resolve_sub_step_context_requirements(
    *, sub: RoutedSubStep, state: PlanExecutionState, step: PlanStep
) -> list[str]:
    """Resolve a router-authored sub-step's declared dependency ids against the
    ids actually present in the state it will be dispatched against.

    The router's LLM occasionally emits a parent-dependency id carrying a
    spurious sub-step suffix (observed live: "21a-2" for the seeded parent
    entry "21a"), which a strict `state.slice` equality match silently drops --
    starving a zero-tool composition sub-step so it fabricates an answer.
    Match exactly first (well-formed sibling + parent refs), then
    suffix-tolerantly (strip a trailing "-<n>" and retry), and finally fall
    back to the parent step's authoritative `depends_on` -- whose entries are
    always seeded into the private state by `_new_private_state`, so an
    all-malformed dep list still reaches the specialist with real data rather
    than nothing."""
    raw = list(sub.context_requirements) or list(sub.depends_on)
    available = {entry.step_id for entry in state.entries}
    resolved: list[str] = []
    seen: set[str] = set()
    for dep_id in raw:
        match = dep_id if dep_id in available else None
        if match is None:
            base = dep_id.rsplit("-", 1)[0]
            if base != dep_id and base in available:
                match = base
        if match is not None and match not in seen:
            seen.add(match)
            resolved.append(match)
    return resolved or list(step.depends_on)


def _sub_step_prep(
    sub: RoutedSubStep, *, user_id: str, context_requirements: list[str], original_user_message: str = ""
) -> StepPrepOutput:
    specific_instructions = [*sub.specific_instructions, _user_id_instruction(user_id)]
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(
            goal=sub.objective,
            description=sub.objective,
            specific_instructions=specific_instructions,
            # A pipeline can end in a composition sub-step, so it needs the same
            # code-decided language directive the synthesis path gets -- see
            # `response_language`. Harmless on a retrieval sub-step.
            tone_language_notes=response_language_directive(original_user_message),
        ),
        context_requirements=context_requirements,
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=None,
    )


def _entry_from_atomic_result(
    *,
    step: PlanStep,
    role: RoleName,
    result: SubagentResult,
    state: PlanExecutionState,
    status: str | None = None,
    warnings: list[str] | None = None,
) -> StateEntry:
    """Atomic path: certainty is exactly whatever the one specialist returned,
    unchanged -- no nested_trace. `status`/`warnings` override the raw
    specialist result so a `succeeded` dispatch that failed the step's own
    success-check is recorded as `partial` (with the unmet criteria) for the
    Monitor to replan."""
    return StateEntry(
        entry_id=f"{step.step_id}-{len(state.entries)}",
        step_id=step.step_id,
        role=role,
        status=status or result.status,
        output_schema_name="generic_step_output_v1",
        data=result.result or {},
        certainty=result.certainty,
        assumptions=result.assumptions,
        warnings=warnings if warnings is not None else result.warnings,
        tool_audit_trail=result.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )


def _new_private_state(*, step: PlanStep, parent_state: PlanExecutionState) -> PlanExecutionState:
    """A fresh private state for one step's pipeline, pre-seeded with the parent
    step's own dependencies -- both the graph-shape ids AND the real entries, so
    a sub-step whose context_requirements names a parent id gets its data, not
    an empty slice."""
    private_state = PlanExecutionState(plan_id=f"{parent_state.plan_id}:{step.step_id}")
    private_state.plan_graph.forward.update({dep_id: [] for dep_id in step.depends_on})
    for parent_entry in parent_state.slice(step.depends_on):
        private_state.append(parent_entry)
    return private_state


async def _execute_pipeline_once(
    *,
    step: PlanStep,
    pipeline: list[RoutedSubStep],
    private_state: PlanExecutionState,
    ctx: TurnContext,
) -> bool:
    """Dispatches one pipeline layer-by-layer (siblings within a layer run
    concurrently), appending each sub-step's entry to `private_state`. Returns
    whether every sub-step succeeded. Stops starting further layers once a
    sub-step falls short -- there is no downstream value in running a layer that
    depends on a failed one, and the partial aggregate goes to the Monitor."""
    sub_by_id = {sub.sub_step_id: sub for sub in pipeline}
    graph = compute_plan_graph([_sub_step_plan_step(sub) for sub in pipeline])

    async def _dispatch_one(sub_step_id: str) -> StateEntry:
        return await _dispatch_pipeline_sub_step(
            sub=sub_by_id[sub_step_id],
            private_state=private_state,
            step=step,
            ctx=ctx,
        )

    all_succeeded = True
    for layer in graph.execution_layers:
        entries = await dispatch_layer_concurrently(layer, _dispatch_one)
        for entry in entries:
            private_state.append(entry)
            if entry.status != "succeeded":
                all_succeeded = False
        if not all_succeeded:
            break
    return all_succeeded


async def _dispatch_pipeline_sub_step(
    *,
    sub: RoutedSubStep,
    private_state: PlanExecutionState,
    step: PlanStep,
    ctx: TurnContext,
) -> StateEntry:
    """One specialist sub-step. Its specialist type is ALREADY decided by the
    router, so -- unlike the old nested path -- there is no per-sub-step
    re-classification call here; we dispatch the named specialist directly."""
    sub_plan_step = _sub_step_plan_step(sub)
    result = await _dispatch_single_specialist(
        step=sub_plan_step,
        step_prep_output=_sub_step_prep(
            sub,
            user_id=ctx.user_id,
            context_requirements=_resolve_sub_step_context_requirements(
                sub=sub, state=private_state, step=step
            ),
            original_user_message=ctx.original_user_message,
        ),
        role=ctx.roles[sub.specialist],
        state=private_state,
        ctx=ctx,
        block_id=ctx.block_id(step.step_id, sub.sub_step_id),
    )
    unmet_criteria: list[str] = []
    criteria_met = False
    if result.status == "succeeded":
        criteria_met, unmet_criteria = await check_success_criteria(
            step=sub_plan_step,
            result=result,
            llm_adapter=ctx.llm,
            block_id=ctx.block_id(step.step_id, sub.sub_step_id, "success-check"),
        )
    status = result.status if criteria_met else "partial"
    warnings = (
        result.warnings
        if criteria_met
        else [*result.warnings, _SUB_STEP_UNMET_MARKER, *unmet_criteria]
    )
    return StateEntry(
        entry_id=f"{sub.sub_step_id}-{len(private_state.entries)}",
        step_id=sub.sub_step_id,
        role=sub.specialist,
        status=status,
        output_schema_name="generic_step_output_v1",
        data=result.result or {},
        certainty=result.certainty,
        assumptions=result.assumptions,
        warnings=warnings,
        tool_audit_trail=result.tool_audit_trail,
        produced_at=datetime.now(timezone.utc),
    )


def _entry_from_pipeline(
    *,
    step: PlanStep,
    state: PlanExecutionState,
    private_state: PlanExecutionState,
    pipeline_succeeded: bool,
    fallback_reason: str | None,
) -> StateEntry:
    """Translates the private pipeline's outcome into the ONE `StateEntry` the
    parent plan sees, with a `nested_trace` (so the Monitor knows to run its
    outer success-criteria re-check). Certainty aggregates via the same
    min-confidence-across-facts convention used elsewhere in this codebase.
    When `pipeline_succeeded` is False, the aggregate is partial/failed and the
    Monitor replans one level up."""
    warnings: list[str] = [fallback_reason] if fallback_reason else []
    succeeded_entries = [entry for entry in private_state.entries if entry.status == "succeeded"]

    if pipeline_succeeded:
        status = "succeeded"
    else:
        warnings.append(_PIPELINE_INCOMPLETE_WARNING)
        status = "partial" if succeeded_entries else "failed"

    if succeeded_entries:
        weakest = min(succeeded_entries, key=lambda entry: entry.certainty.confidence)
        certainty = CertaintyTag(basis=weakest.certainty.basis, confidence=weakest.certainty.confidence)
    else:
        certainty = CertaintyTag(basis="llm_interpretation", confidence=0.0)

    # loop.py's composition short-circuit + routes/advise.py's final-answer
    # extraction both do a flat `data.get("answer_text")` on any composition
    # entry, so when the pipeline genuinely ended in a composition sub-step,
    # surface that sub-step's own data flat; otherwise wrap sub-results.
    role: RoleName = succeeded_entries[-1].role if succeeded_entries else "retrieval"
    if succeeded_entries and role == "composition":
        data = succeeded_entries[-1].data
    else:
        data = {"sub_results": {entry.step_id: entry.data for entry in succeeded_entries}}

    all_warnings = [*warnings, *(w for entry in private_state.entries for w in entry.warnings)]
    all_assumptions = [a for entry in private_state.entries for a in entry.assumptions]
    all_tool_audit = [record for entry in private_state.entries for record in entry.tool_audit_trail]

    nested_trace = NestedExecutionTrace(
        private_plan_id=private_state.plan_id,
        rounds_used=1,
        rounds_exhausted=not pipeline_succeeded,
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


__all__ = ["run_task_handler"]
