"""Optional diagnostic integration: Planner Agent (Phase 5).

Diagnostic only, mirroring `app.agent.task_understanding.integration` and
`app.agent.capabilities.diagnostics`. Runs the Planner Agent and the Phase 4
`ContextCompiler` (to preview, never execute, context for each planned
subtask), then produces a small, compact summary meant to be attached to
`agent_runs.retrievalMetadata.plannerDiagnostics`.

Hard constraints:
- Never selects a workflow or executes a subtask/tool.
- Never changes the final response or emits new SSE events.
- Never raises into a live turn — any failure degrades to `None`.
- No raw compiled context, raw LLM prompts, raw reasoning passes, or
  chain-of-thought is ever included in the returned summary.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.context_compiler.compiler import compile_context_for_capability
from app.agent.context_compiler.schemas import ContextCompilationRequest
from app.agent.planner.dynamic_spec_diagnostics import build_planner_dynamic_agents_metadata
from app.agent.planner.agent import build_execution_plan
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_MAX_WARNINGS_LOGGED = 8
_MAX_MISSING_CONTEXT_LOGGED = 8
_MAX_CONTEXT_PREVIEWS = 12


def _context_preview_for_subtask(
    subtask: PlannerSubtask, *, registry: CapabilityRegistry
) -> dict[str, Any] | None:
    """Compact, storage-safe preview of what `ContextCompiler` would hand this subtask.

    Never includes the actual compiled context payload — only section names,
    warnings, and a rough item count.
    """
    try:
        request = ContextCompilationRequest(
            capability_name=subtask.capability_name,
            objective=subtask.objective,
            user_message="",
        )
        compiled = compile_context_for_capability(request, registry=registry)
    except Exception:  # noqa: BLE001 — a preview failure must never break diagnostics
        logger.exception("planner_context_preview_failed", extra={"subtaskId": subtask.id})
        return None

    return {
        "subtaskId": subtask.id,
        "capabilityName": compiled.capability_name,
        "includedSections": compiled.included_sections,
        "omittedSections": compiled.omitted_sections[:_MAX_CONTEXT_PREVIEWS],
        "warnings": compiled.warnings[:_MAX_CONTEXT_PREVIEWS],
        "estimatedItems": compiled.estimated_items,
    }


def _diagnostic_summary(plan: PlannerOutput, *, registry: CapabilityRegistry) -> dict[str, Any]:
    context_previews = []
    for subtask in plan.subtasks[:_MAX_CONTEXT_PREVIEWS]:
        preview = _context_preview_for_subtask(subtask, registry=registry)
        if preview is not None:
            context_previews.append(preview)

    return {
        "status": plan.status,
        "planId": plan.plan_id,
        "executionMode": plan.execution_mode,
        "recommendedAutonomyLevel": plan.recommended_autonomy_level,
        "primaryIntent": plan.primary_intent,
        "subtaskCount": len(plan.subtasks),
        "capabilities": [subtask.capability_name for subtask in plan.subtasks],
        "requiresUserConfirmation": plan.requires_user_confirmation,
        "writeRisk": plan.write_risk,
        "missingContext": plan.missing_context[:_MAX_MISSING_CONTEXT_LOGGED],
        "warnings": plan.warnings[:_MAX_WARNINGS_LOGGED],
        "confidence": plan.confidence,
        "source": plan.source,
        "contextPreviews": context_previews,
    }


async def build_plan_with_diagnostics(
    *,
    user_message: str,
    task_understanding_summary: dict[str, Any] | None,
    deterministic_intent: str | None,
    deterministic_entities: dict[str, Any] | None,
    conversation_entities: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    legacy_workflow_plan: dict[str, Any] | None = None,
    profile_summary: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> tuple[PlannerOutput | None, dict[str, Any] | None]:
    """Run the Planner Agent, returning both the full plan and its diagnostic summary.

    Returns `(None, None)` when the feature flag is off or the run fails.
    Never raises — see `run_planner_dry_run` (the summary-only wrapper most
    callers should use; `orchestrator.py`'s Phase 6 supervisor integration
    is the one caller that also needs the full `PlannerOutput`, since
    `SupervisorRunInput.planner_output` needs the full subtask graph, not a
    diagnostic rollup of it).
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_planner_enabled():
        return None, None

    try:
        registry = build_default_capability_registry()
        plan = await build_execution_plan(
            user_message=user_message,
            task_understanding=task_understanding_summary or {},
            deterministic_intent=deterministic_intent,
            deterministic_entities=deterministic_entities,
            conversation_entities=conversation_entities,
            conversation_assumptions=conversation_assumptions,
            legacy_workflow_plan=legacy_workflow_plan,
            capability_registry=registry,
            profile_summary=profile_summary,
            settings=cfg,
        )
        summary = _diagnostic_summary(plan, registry=registry)
        planner_dynamic = build_planner_dynamic_agents_metadata(plan.dynamic_spec_diagnostics)
        if planner_dynamic is not None:
            summary["plannerDynamicAgents"] = planner_dynamic
    except Exception:  # noqa: BLE001 — diagnostic-only path, must never break a live turn
        logger.exception("planner_dry_run_failed")
        return None, None

    logger.info("planner_dry_run_result", extra={"plannerDiagnostics": summary})
    return plan, summary


async def run_planner_dry_run(
    *,
    user_message: str,
    task_understanding_summary: dict[str, Any] | None,
    deterministic_intent: str | None,
    deterministic_entities: dict[str, Any] | None,
    conversation_entities: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    legacy_workflow_plan: dict[str, Any] | None = None,
    profile_summary: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Run the Planner Agent for diagnostics only (summary-only convenience wrapper).

    Returns a compact summary dict (safe to log or store in
    `agent_runs.retrievalMetadata`), or `None` when the feature flag is off
    or the diagnostic run itself fails. Behavior is unchanged from Phase 5.
    """
    _plan, summary = await build_plan_with_diagnostics(
        user_message=user_message,
        task_understanding_summary=task_understanding_summary,
        deterministic_intent=deterministic_intent,
        deterministic_entities=deterministic_entities,
        conversation_entities=conversation_entities,
        conversation_assumptions=conversation_assumptions,
        legacy_workflow_plan=legacy_workflow_plan,
        profile_summary=profile_summary,
        settings=settings,
    )
    return summary
