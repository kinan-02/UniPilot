"""Compact plan repair diagnostics (Phase 19)."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.planner.plan_delta import delta_from_clarification_resolution, deltas_from_monitor_diagnostics
from app.agent.planner.plan_snapshot import build_fallback_plan_snapshot, build_plan_snapshot_from_planner_output
from app.agent.planner.repair_agent import build_plan_repair_request, run_plan_repair
from app.agent.planner.repair_policy import choose_repair_mode
from app.agent.planner.repair_schemas import PlanRepairOutput, PlanRepairRequest
from app.agent.planner.replan_cycle_budget import (
    apply_replan_cycle_bounds,
    build_replan_cycle_budget,
    build_replan_cycle_metadata,
)
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_MAX_WARNINGS = 8


def build_plan_repair_metadata(
    output: PlanRepairOutput,
    *,
    request: PlanRepairRequest | None = None,
    replan_cycle: dict[str, str | int | bool | None] | None = None,
) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.planRepairDiagnostics`."""
    delta_kinds = sorted({delta.kind for delta in request.deltas}) if request is not None else []
    metadata: dict[str, Any] = {
        "status": output.status,
        "modeUsed": output.mode_used,
        "safeToUse": output.safe_to_use,
        "deltaCount": len(request.deltas) if request is not None else 0,
        "deltaKinds": delta_kinds,
        "preservedSubtaskCount": len(output.preserved_subtask_ids),
        "revisedSubtaskCount": len(output.revised_subtask_ids),
        "addedSubtaskCount": len(output.added_subtask_ids),
        "removedSubtaskCount": len(output.removed_subtask_ids),
        "reasonCodes": list(output.reason_codes[:12]),
        "warnings": list(output.warnings[:_MAX_WARNINGS]),
    }
    if replan_cycle is not None:
        metadata["replanCycle"] = replan_cycle
    return metadata


async def run_plan_repair_diagnostics(
    *,
    user_goal: str,
    planner_output: dict[str, Any] | None,
    monitor_metadata: dict[str, Any] | None,
    workflow_name: str | None = None,
    intent: str | None = None,
    clarification_state_metadata: dict[str, Any] | None = None,
    confirmed_clarification_answers: list[dict[str, Any]] | None = None,
    clarification_assumptions_created: list[dict[str, Any]] | None = None,
    original_user_message: str | None = None,
    current_user_message: str | None = None,
    settings: Settings | None = None,
) -> tuple[PlanRepairOutput | None, dict[str, Any] | None]:
    """Run diagnostic plan repair when enabled. Never raises."""
    cfg = settings or get_settings()
    if not cfg.is_agent_plan_repair_enabled():
        return None, None

    dry_run = cfg.is_agent_plan_repair_dry_run()
    warnings: list[str] = []
    if not cfg.agent_plan_repair_dry_run:
        dry_run = True
        warnings.append("plan_repair_forced_dry_run")

    try:
        prior = None
        if isinstance(planner_output, dict):
            prior = build_plan_snapshot_from_planner_output(planner_output)
        if prior is None:
            prior = build_fallback_plan_snapshot(
                user_goal=user_goal,
                workflow_name=workflow_name,
                intent=intent,
            )

        deltas = deltas_from_monitor_diagnostics(monitor_metadata or {})
        if clarification_state_metadata and confirmed_clarification_answers:
            clarification_delta = delta_from_clarification_resolution(
                clarification_state_metadata=clarification_state_metadata,
                confirmed_answers=confirmed_clarification_answers,
                assumptions_created=clarification_assumptions_created,
            )
            if clarification_delta is not None:
                deltas.append(clarification_delta)

        request = build_plan_repair_request(
            prior_plan_snapshot=prior,
            user_goal=user_goal,
            deltas=deltas,
            monitor_decision=(monitor_metadata or {}).get("decision") if isinstance(monitor_metadata, dict) else {},
            confirmed_clarifications=confirmed_clarification_answers,
            original_user_message=original_user_message,
            current_user_message=current_user_message,
            dry_run=dry_run,
        )

        proposed_mode = choose_repair_mode(request)
        cycle_budget = build_replan_cycle_budget(
            user_goal=user_goal,
            max_repairs=cfg.resolved_agent_replan_max_repairs_per_goal(),
            max_regenerations=cfg.resolved_agent_replan_max_regenerations_per_goal(),
        )
        cycle_decision = apply_replan_cycle_bounds(
            budget=cycle_budget,
            proposed_mode=proposed_mode,
            deltas=deltas,
        )
        bounded_request = request.model_copy(update={"requested_mode": cycle_decision.effective_mode})

        output = await run_plan_repair(bounded_request, settings=cfg)
        if warnings:
            output = output.model_copy(update={"warnings": [*output.warnings, *warnings]})
        if cycle_decision.bounded:
            output = output.model_copy(
                update={
                    "warnings": [
                        *output.warnings,
                        f"replan_cycle_bounded:{cycle_decision.escalation_action}",
                    ]
                }
            )
        metadata = build_plan_repair_metadata(
            output,
            request=request,
            replan_cycle=build_replan_cycle_metadata(cycle_decision),
        )
        logger.info("plan_repair_diagnostics_result", extra={"planRepairDiagnostics": metadata})
        return output, metadata
    except Exception:  # noqa: BLE001 — diagnostic-only path
        logger.exception("plan_repair_diagnostics_failed")
        return None, None
