"""Supervisor Orchestrator Runtime (Phase 6/7) — shadow-only by default.

Consumes a normalized `PlannerOutput` (Phase 5) and executes its subtask
graph *mechanics*: dependency ordering, context compilation per subtask,
handler dispatch, blackboard updates, retry/budget enforcement, and compact
diagnostics. Independent subtasks (same dependency "wave" — no unmet
dependency between them) are dispatched concurrently via `asyncio.gather`;
only cross-wave ordering is serialized.

Hard constraints (enforced by construction, not just by convention):
- Every Phase 6 built-in handler (`app.agent.supervisor.handlers`) is a safe
  dry-run stand-in. Phase 7 adds real execution for a small, explicitly
  reviewed set of read-only workflows
  (`app.agent.supervisor.workflow_adapters.ReadOnlyWorkflowAdapterHandler`),
  gated by `app.agent.supervisor.safety.can_shadow_execute_capability` *and*
  by whether a populated `SupervisorRuntimeContext` (real database + real
  `AgentContextPack`) was supplied — this runtime never reconstructs those
  from compiled context, and never runs a real handler without them.
- No capability may create an action proposal or perform a write from this
  runtime by *default* — `safety.can_shadow_execute_capability` hard-fails
  any capability with `can_create_action_proposals=True`,
  `can_execute_writes=True`, or `write_scope != "none"`, and this is the
  *only* safety check consulted unless a caller explicitly passes
  `run_supervisor_shadow(..., allow_proposal_capable_execution=True)`.
  Post-Phase-9: that opt-in additionally requires
  `safety.can_execute_capability_for_real_with_proposals` to independently
  pass, and even then only tolerates a proposed action if the specific
  handler instance registered for that capability was itself explicitly
  constructed to allow one (`ReadOnlyWorkflowAdapterHandler(allow_single_proposed_action=True)`)
  — never a direct write (`can_execute_writes`/non-`"proposal_only"` scope
  are still hard-blocked regardless). Only
  `app.agent.planner_first_live.run_planner_first_live_turn` ever passes
  this opt-in, and only after its own independent eligibility gate. Every
  other caller (`supervisor/diagnostics.py`, `supervisor/post_context_runner.py`)
  never does, so this runtime remains fully incapable of creating a
  proposal or performing a write for the shadow-compare/promotion/
  diagnostic pipeline.
- No LLM calls anywhere in this module or its collaborators.
- Never used by `orchestrator.run_agent_turn` to select a workflow or shape
  the live response for the shadow-compare/diagnostic path — see
  `supervisor/diagnostics.py` for that (optional, diagnostic-only)
  integration. `app.agent.planner_first_live` is the one, separately
  gated, exception that *does* let this runtime's real output become the
  live response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityDescriptor
from app.agent.context_compiler.compiler import compile_context_for_capability
from app.agent.context_compiler.schemas import CompiledContext, ContextCompilationRequest
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.budgets import BudgetTracker
from app.agent.supervisor.controller import decide_next_action
from app.agent.supervisor.errors import InvalidPlannerOutputError, SupervisorError
from app.agent.supervisor.graph import ExecutionGraph
from app.agent.supervisor.handler_registry import (
    SubtaskHandlerRegistry,
    UnsupportedCapabilityHandler,
    build_default_handler_registry,
)
from app.agent.supervisor.handlers import DryRunCapabilityHandler, SubtaskHandler
from app.agent.supervisor.safety import (
    can_execute_capability_for_real_with_proposals,
    can_shadow_execute_capability,
    shadow_execution_blocked_warning,
)
from app.agent.supervisor.schemas import (
    SubtaskExecutionRecord,
    SubtaskResult,
    SupervisorRunInput,
    SupervisorRunOutput,
    SupervisorRunStatus,
    SupervisorRuntimeContext,
)
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_UNSUPPORTED_HANDLER = UnsupportedCapabilityHandler()
_DRY_RUN_FALLBACK_HANDLER = DryRunCapabilityHandler()


def _parse_planner_output(raw: dict[str, Any]) -> PlannerOutput:
    try:
        return PlannerOutput.model_validate(raw)
    except ValidationError as exc:
        raise InvalidPlannerOutputError(f"invalid_planner_output: {exc}") from exc


def _compile_context_preview(
    subtask: PlannerSubtask, *, registry: CapabilityRegistry
) -> tuple[CompiledContext, dict[str, Any]]:
    request = ContextCompilationRequest(
        capability_name=subtask.capability_name,
        objective=subtask.objective,
        user_message="",
    )
    compiled = compile_context_for_capability(request, registry=registry)
    preview = {
        "includedSections": compiled.included_sections,
        "omittedSections": compiled.omitted_sections,
        "warnings": compiled.warnings,
        "estimatedItems": compiled.estimated_items,
    }
    return compiled, preview


def _select_handler(
    capability: CapabilityDescriptor,
    *,
    handlers: SubtaskHandlerRegistry,
    real_handlers_enabled: bool,
    runtime_context: SupervisorRuntimeContext | None,
    allow_proposal_capable_execution: bool = False,
    real_execution_allowed_capability_names: frozenset[str] | None = None,
) -> tuple[SubtaskHandler | None, str | None]:
    """Resolve the handler to actually call for `capability`.

    When `real_handlers_enabled` is `False`, or `capability.type` isn't
    `"workflow"`, this is exactly the registry's normal by-name/by-type/
    default resolution — Phase 6 behavior, unchanged.

    When `real_handlers_enabled` is `True` and `capability.type == "workflow"`,
    *every* workflow capability is safety-checked — not just the ones a
    caller happened to pre-register a real adapter for:
    - `real_execution_allowed_capability_names` not `None` and
      `capability.name` not in it -> the safe dry-run fallback handler
      (Layer 2 / Planner-first-live multi-capability dispatch: this is a
      *governance* allowlist, distinct from the safety checks below — a
      capability can be perfectly safe per its own descriptor metadata yet
      still not be one the readiness manifest has specifically approved for
      real dispatch this turn). `None` (the default, used by every caller
      except `run_planner_first_live_turn`) skips this check entirely,
      preserving Phase 6/7 behavior exactly.
    - unsafe for both real-execution modes (`safety.can_shadow_execute_capability`
      is `False`, *and* either `allow_proposal_capable_execution` is `False`
      or `safety.can_execute_capability_for_real_with_proposals` is `False`)
      -> `(None, blocked_warning)`. Never falls back to dry-run for this
      case — an explicit `"skipped"` result is more honest than silently
      running the Phase 6 dry-run summary for a capability that was
      actually refused real execution. `allow_proposal_capable_execution`
      only ever widens this check for a capability that is *also* marked
      `real_execution_supported_with_proposals` — it can never make an
      otherwise-unsafe capability dispatchable.
    - safe, but marked `execution.operationally_expensive_for_shadow_execution`
      (Phase 8 — e.g. `general_academic_workflow`, which may call an LLM) ->
      the safe dry-run fallback handler, with a warning explaining why. This
      is independent of `runtime_context` availability: even a fully
      populated context never triggers a real call for an expensive
      capability by default, so post-context shadow comparison can never
      introduce a surprise LLM call.
    - safe, not expensive, but no usable `runtime_context` -> the safe
      dry-run fallback handler, with a warning explaining why.
    - safe, not expensive, and a usable `runtime_context` is available ->
      the real `ReadOnlyWorkflowAdapterHandler` (the registry's own
      registered instance if it has one for this capability name, so a
      caller-supplied `workflow_lookup` is respected; a fresh default
      instance otherwise -- note the fresh default instance never tolerates
      a proposed action regardless of `allow_proposal_capable_execution`;
      only an explicitly pre-registered, purpose-configured instance ever
      can, since that flag alone only controls whether dispatch is even
      reached, never what a handler instance itself tolerates).

    Layer 3: `capability.type == "specialist_agent"` also gets the
    `real_execution_allowed_capability_names` allowlist re-check above (a
    defense-in-depth backstop for `run_planner_first_live_turn`'s own
    specialist-agent dispatch, mirroring the workflow path's independent
    re-validation) -- but none of the workflow-specific safety checks below
    (`can_shadow_execute_capability`, `operationally_expensive_for_shadow_execution`,
    `ReadOnlyWorkflowAdapterHandler` resolution), since those don't apply to
    a specialist agent. Specialist-specific safety
    (`specialists.safety.is_specialist_agent_safe`) is independently
    re-checked inside `SpecialistAgentHandler.run()` itself, every call,
    regardless of this allowlist.
    """
    if not real_handlers_enabled or capability.type not in {"workflow", "specialist_agent"}:
        return handlers.resolve(capability_name=capability.name, capability_type=capability.type), None

    if (
        real_execution_allowed_capability_names is not None
        and capability.name not in real_execution_allowed_capability_names
    ):
        return (
            _DRY_RUN_FALLBACK_HANDLER,
            f"real_shadow_execution_skipped_not_allowlisted: {capability.name}",
        )

    if capability.type != "workflow":
        return handlers.resolve(capability_name=capability.name, capability_type=capability.type), None

    read_only_safe = can_shadow_execute_capability(capability)
    proposal_capable_safe = allow_proposal_capable_execution and can_execute_capability_for_real_with_proposals(
        capability
    )
    if not read_only_safe and not proposal_capable_safe:
        return None, shadow_execution_blocked_warning(capability.name)

    if capability.execution.operationally_expensive_for_shadow_execution:
        return (
            _DRY_RUN_FALLBACK_HANDLER,
            f"real_shadow_execution_skipped_operationally_expensive: {capability.name}",
        )

    if (
        runtime_context is None
        or runtime_context.database is None
        or runtime_context.agent_context_pack is None
    ):
        return _DRY_RUN_FALLBACK_HANDLER, "real_shadow_execution_unavailable_missing_runtime_context"

    resolved = handlers.resolve(capability_name=capability.name, capability_type=capability.type)
    if isinstance(resolved, ReadOnlyWorkflowAdapterHandler):
        return resolved, None
    return ReadOnlyWorkflowAdapterHandler(), None


async def _run_subtask(
    subtask: PlannerSubtask,
    *,
    registry: CapabilityRegistry,
    handlers: SubtaskHandlerRegistry,
    blackboard: SupervisorBlackboard,
    budget: BudgetTracker,
    dry_run: bool,
    record: SubtaskExecutionRecord,
    real_handlers_enabled: bool = False,
    runtime_context: SupervisorRuntimeContext | None = None,
    allow_proposal_capable_execution: bool = False,
    real_execution_allowed_capability_names: frozenset[str] | None = None,
) -> tuple[SubtaskResult, SubtaskExecutionRecord, bool]:
    """Run one subtask (with retries), returning `(result, record, hit_global_retry_limit)`.

    `hit_global_retry_limit` is `True` only when a retry would otherwise
    have been allowed for *this* subtask (its own per-subtask budget still
    had room) but the *shared* `max_total_retries` budget was exhausted —
    the caller treats that specifically as a run-level `budget_exceeded`,
    distinct from an ordinary "no more retries for this one subtask".
    """
    started_at_ms = budget.elapsed_ms()
    budget.record_subtask_started()

    capability = registry.get(subtask.capability_name)
    if capability is None or not capability.enabled:
        result = await _UNSUPPORTED_HANDLER.run(
            subtask=subtask, compiled_context=None, blackboard=blackboard, dry_run=dry_run
        )
        record = record.model_copy(
            update={
                "status": "skipped",
                "attempts": 1,
                "started_at_ms": started_at_ms,
                "completed_at_ms": budget.elapsed_ms(),
                "result_summary": result.output_summary,
                "warnings": result.warnings,
            }
        )
        return result, record, False

    handler, blocked_or_fallback_warning = _select_handler(
        capability,
        handlers=handlers,
        real_handlers_enabled=real_handlers_enabled,
        runtime_context=runtime_context,
        allow_proposal_capable_execution=allow_proposal_capable_execution,
        real_execution_allowed_capability_names=real_execution_allowed_capability_names,
    )
    if handler is None:
        # Explicitly unsafe for real execution -- never dry-run fallback,
        # never retried, just a clean, honest skip.
        result = SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="skipped",
            output_summary={
                "shadowExecuted": False,
                "reason": "Capability may create proposed actions; real shadow execution deferred.",
            },
            warnings=[blocked_or_fallback_warning] if blocked_or_fallback_warning else [],
        )
        record = record.model_copy(
            update={
                "status": "skipped",
                "attempts": 1,
                "started_at_ms": started_at_ms,
                "completed_at_ms": budget.elapsed_ms(),
                "result_summary": result.output_summary,
                "warnings": result.warnings,
            }
        )
        return result, record, False

    compiled_context: CompiledContext | None = None
    context_preview: dict[str, Any] | None = None
    if budget.can_compile_context_preview():
        try:
            compiled_context, context_preview = _compile_context_preview(subtask, registry=registry)
            budget.record_context_preview()
        except Exception:  # noqa: BLE001 — a preview failure must never crash the run
            logger.exception("supervisor_context_preview_failed", extra={"subtaskId": subtask.id})
            context_preview = {"error": "context_compilation_failed"}
    else:
        context_preview = {"omitted": "max_context_previews_budget_reached"}

    attempts = 0
    hit_global_retry_limit = False
    result: SubtaskResult
    handler_warnings = [blocked_or_fallback_warning] if blocked_or_fallback_warning else []

    while True:
        attempts += 1
        if compiled_context is None:
            result = SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="failed",
                error="context_unavailable",
                confidence=0.0,
            )
        else:
            try:
                result = await handler.run(
                    subtask=subtask,
                    compiled_context=compiled_context,
                    blackboard=blackboard,
                    dry_run=dry_run,
                    runtime_context=runtime_context,
                )
                if handler_warnings:
                    result = result.model_copy(
                        update={"warnings": [*handler_warnings, *result.warnings]}
                    )
            except Exception as exc:  # noqa: BLE001 — a handler bug must never crash the run
                logger.exception("supervisor_handler_failed", extra={"subtaskId": subtask.id})
                result = SubtaskResult(
                    subtask_id=subtask.id,
                    capability_name=subtask.capability_name,
                    status="failed",
                    error=str(exc),
                    confidence=0.0,
                )

        if result.status != "failed":
            break
        if budget.can_retry(subtask.id):
            budget.record_retry(subtask.id)
            continue
        if budget.per_subtask_retry_available(subtask.id) and not budget.total_retry_available():
            hit_global_retry_limit = True
        break

    record = record.model_copy(
        update={
            "status": result.status,
            "attempts": attempts,
            "started_at_ms": started_at_ms,
            "completed_at_ms": budget.elapsed_ms(),
            "context_preview": context_preview,
            "result_summary": result.output_summary,
            "warnings": result.warnings,
            "error": result.error,
        }
    )
    return result, record, hit_global_retry_limit


def _skip_remaining(
    order: list[str],
    *,
    records: dict[str, SubtaskExecutionRecord],
    handled: set[str],
    skipped: set[str],
) -> None:
    """Mark every not-yet-handled subtask as skipped (used when the run stops early)."""
    for subtask_id in order:
        if subtask_id in handled:
            continue
        records[subtask_id] = records[subtask_id].model_copy(update={"status": "skipped"})
        handled.add(subtask_id)
        skipped.add(subtask_id)


def _failure_output(
    *,
    plan_id: str,
    execution_mode: str,
    error: str,
    warnings: list[str],
    blackboard_summary: dict[str, Any] | None = None,
) -> SupervisorRunOutput:
    return SupervisorRunOutput(
        status="failed",
        plan_id=plan_id,
        execution_mode=execution_mode,
        errors=[error],
        warnings=warnings,
        blackboard_summary=blackboard_summary or {},
        diagnostics={"reason": error},
    )


async def run_supervisor_shadow(
    *,
    input: SupervisorRunInput,
    capability_registry: CapabilityRegistry | None = None,
    handler_registry: SubtaskHandlerRegistry | None = None,
    runtime_context: SupervisorRuntimeContext | None = None,
    settings: Settings | None = None,
    allow_proposal_capable_execution: bool = False,
    real_execution_allowed_capability_names: frozenset[str] | None = None,
) -> SupervisorRunOutput:
    """Run a normalized `PlannerOutput`'s subtask graph mechanics — shadow-only
    by default.

    Never creates an action proposal or performs a write; every built-in
    Phase 6 handler is a safe dry-run stand-in, and Phase 7's real
    `ReadOnlyWorkflowAdapterHandler` is only ever used for a capability that
    passes `safety.can_shadow_execute_capability` *and* only when
    `runtime_context` supplies a real database + `AgentContextPack` — this
    function never reconstructs either from compiled context. Never raises:
    structural problems (invalid `planner_output`, duplicate ids, unknown
    dependencies, dependency cycles) resolve to a `status="failed"` output
    instead of an exception, and a subtask handler bug resolves to that
    subtask failing, not to the whole call raising.

    If `handler_registry` is not supplied, the default registry is built
    with real read-only handlers enabled only when
    `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true` — when that flag is off
    (the default), behavior is identical to Phase 6.

    `allow_proposal_capable_execution` (post-Phase-9, default `False`) is a
    second, independent opt-in: even when `True`, a capability only
    dispatches for real if it *also* passes
    `safety.can_execute_capability_for_real_with_proposals` (which
    `can_shadow_execute_capability` never does for a proposal-creating
    capability) -- and even then, whether a produced proposed action is
    actually tolerated or treated as a failure is controlled entirely by
    the handler instance the caller registered (`allow_single_proposed_action`
    on `workflow_adapters.ReadOnlyWorkflowAdapterHandler`), not by this flag
    alone. Only `app.agent.planner_first_live.run_planner_first_live_turn`
    ever passes `True` here, and only after its own independent eligibility
    gate has already passed. Every other caller (diagnostics, promotion,
    shadow-compare) leaves this at the default `False`, so this call can
    never create a proposal for them.

    `real_execution_allowed_capability_names` (default `None`) is a second,
    independent governance allowlist threaded straight to `_select_handler`
    — when supplied, a workflow capability that is otherwise safety-eligible
    for real execution still degrades to the dry-run fallback unless its
    name is in this set. Only `run_planner_first_live_turn` ever supplies
    this (derived from which capabilities in its plan actually passed the
    readiness-manifest eligibility check); every other caller leaves it
    `None`, which skips the check entirely and preserves prior behavior.
    """
    cfg = settings or get_settings()
    real_handlers_enabled = cfg.is_agent_supervisor_real_handlers_enabled()
    registry = capability_registry or build_default_capability_registry()
    handlers = handler_registry or build_default_handler_registry(
        enable_real_read_only_handlers=real_handlers_enabled, settings=cfg
    )
    budget = BudgetTracker(input.budget)

    warnings: list[str] = []
    if not input.dry_run:
        # `input.dry_run` is not read by any handler (built-in Phase 6
        # handlers are unconditionally dry-run stand-ins; Phase 7's real
        # `ReadOnlyWorkflowAdapterHandler` is gated solely by
        # `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` + `safety
        # .can_shadow_execute_capability`, independent of this flag) --
        # surface that loudly instead of letting a caller believe setting
        # it to `False` changes execution behavior in this runtime.
        warnings.append("supervisor_dry_run_flag_has_no_effect_on_shadow_execution")

    fallback_plan_id = str(input.planner_output.get("plan_id") or "unknown")
    fallback_execution_mode = str(input.planner_output.get("execution_mode") or "unsupported")

    try:
        plan = _parse_planner_output(input.planner_output)
    except SupervisorError as exc:
        return _failure_output(
            plan_id=fallback_plan_id,
            execution_mode=fallback_execution_mode,
            error=str(exc),
            warnings=warnings,
        )

    blackboard = SupervisorBlackboard(
        original_user_message=input.user_message,
        task_understanding=input.task_understanding,
        planner_output=input.planner_output,
        profile_summary=input.profile_summary,
    )
    for assumption in input.conversation_assumptions:
        blackboard.add_assumption(assumption)

    try:
        graph = ExecutionGraph.build(plan.subtasks)
    except SupervisorError as exc:
        return _failure_output(
            plan_id=plan.plan_id,
            execution_mode=plan.execution_mode,
            error=str(exc),
            warnings=warnings,
            blackboard_summary=blackboard.to_summary(),
        )

    order = graph.topological_order()
    records: dict[str, SubtaskExecutionRecord] = {
        subtask_id: SubtaskExecutionRecord(
            subtask_id=subtask_id,
            capability_name=graph.get(subtask_id).capability_name,
            status="pending",
            depends_on=graph.dependencies_of(subtask_id),
        )
        for subtask_id in order
    }

    completed: set[str] = set()
    failed: set[str] = set()
    skipped: set[str] = set()
    handled: set[str] = set()
    errors: list[str] = []
    run_status: SupervisorRunStatus = "completed"

    # Dispatch by dependency "wave": every subtask whose dependencies are
    # already satisfied runs concurrently (they're independent by
    # definition — that's what makes them simultaneously ready); only
    # cross-wave ordering is serialized. A wave fully completes (via
    # `asyncio.gather`) before its results are evaluated, so a stop
    # condition raised by one member never cancels its wave-mates —
    # concurrent siblings have no dependency relationship to preserve by
    # cutting them off mid-flight.
    while True:
        if budget.runtime_exceeded():
            run_status = "budget_exceeded"
            warnings.append("budget_exceeded: max_runtime_ms")
            _skip_remaining(order, records=records, handled=handled, skipped=skipped)
            break

        ready = [
            subtask_id
            for subtask_id in graph.ready_subtasks(completed=completed, blocked=failed | skipped)
            if subtask_id not in handled
        ]
        if not ready:
            # `ready_subtasks` excludes anything whose dependencies aren't
            # all in `completed` — it doesn't itself mark those subtasks
            # skipped. If unhandled subtasks remain here, every one of them
            # is transitively blocked by a failed/skipped dependency (a
            # dependency-cycle would already have been rejected at
            # `ExecutionGraph.build()`), so resolve them explicitly rather
            # than silently leaving them "pending" forever.
            for subtask_id in order:
                if subtask_id not in handled:
                    blackboard.add_warning(f"subtask_skipped_blocked_dependency: {subtask_id}")
            _skip_remaining(order, records=records, handled=handled, skipped=skipped)
            break

        if budget.subtasks_exceeded():
            run_status = "budget_exceeded"
            warnings.append("budget_exceeded: max_subtasks")
            _skip_remaining(order, records=records, handled=handled, skipped=skipped)
            break

        remaining_budget = max(0, budget.budget.max_subtasks - budget.subtasks_started)
        wave = ready[:remaining_budget]
        if not wave:
            run_status = "budget_exceeded"
            warnings.append("budget_exceeded: max_subtasks")
            _skip_remaining(order, records=records, handled=handled, skipped=skipped)
            break

        wave_results = await asyncio.gather(
            *(
                _run_subtask(
                    graph.get(subtask_id),
                    registry=registry,
                    handlers=handlers,
                    blackboard=blackboard,
                    budget=budget,
                    dry_run=input.dry_run,
                    record=records[subtask_id],
                    real_handlers_enabled=real_handlers_enabled,
                    runtime_context=runtime_context,
                    allow_proposal_capable_execution=allow_proposal_capable_execution,
                    real_execution_allowed_capability_names=real_execution_allowed_capability_names,
                )
                for subtask_id in wave
            )
        )

        stop_run = False
        for subtask_id, (result, record, hit_global_retry_limit) in zip(wave, wave_results, strict=True):
            records[subtask_id] = record
            blackboard.add_subtask_result(result)
            handled.add(subtask_id)

            if result.status == "completed":
                completed.add(subtask_id)
                continue
            if result.status == "skipped":
                skipped.add(subtask_id)
                continue

            failed.add(subtask_id)
            if hit_global_retry_limit:
                run_status = "budget_exceeded"
                warnings.append("budget_exceeded: max_total_retries")
                errors.append(f"subtask_failed: {subtask_id}")
                stop_run = True
                continue

            decision = decide_next_action(
                result, subtask_id=subtask_id, budget=budget, total_subtasks=len(order)
            )
            if decision == "fail_run":
                run_status = "failed"
                errors.append(f"subtask_failed: {subtask_id}")
                stop_run = True
            # "skip_dependents" is realized by `ready_subtasks`'s `blocked`
            # filter on the next wave -- nothing more to do here.

        if stop_run:
            _skip_remaining(order, records=records, handled=handled, skipped=skipped)
            break

    if run_status == "completed" and (failed or skipped or warnings or blackboard.warnings):
        run_status = "completed_with_warnings"

    diagnostics = {"budget": budget.to_summary()}

    return SupervisorRunOutput(
        status=run_status,
        plan_id=plan.plan_id,
        execution_mode=plan.execution_mode,
        subtask_records=[records[subtask_id] for subtask_id in order],
        completed_subtasks=[sid for sid in order if sid in completed],
        failed_subtasks=[sid for sid in order if sid in failed],
        skipped_subtasks=[sid for sid in order if sid in skipped],
        blackboard_summary=blackboard.to_summary(),
        warnings=list(dict.fromkeys([*warnings, *blackboard.warnings])),
        errors=list(dict.fromkeys([*errors, *blackboard.errors])),
        diagnostics=diagnostics,
    )
