"""Deterministic plan repair fallback (Phase 19).

Never calls an LLM. Diagnostic-only — `safe_to_use` stays false by default.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from app.agent.planner.repair_policy import choose_repair_mode
from app.agent.planner.repair_schemas import PlanRepairOutput, PlanRepairRequest, PlanRepairStatus, RepairMode


def _status_for_mode(mode: RepairMode) -> PlanRepairStatus:
    mapping: dict[RepairMode, PlanRepairStatus] = {
        "continue": "continued",
        "abort_safely": "aborted_safely",
        "clarify_first": "clarification_needed",
        "repair": "repaired",
        "regenerate": "regenerated",
    }
    return mapping[mode]


def _affected_subtask_ids(request: PlanRepairRequest) -> set[str]:
    affected: set[str] = set()
    for delta in request.deltas:
        affected.update(str(item) for item in delta.affected_subtask_ids if str(item).strip())
    return affected


def _merge_confirmed_clarifications(plan: dict[str, Any], request: PlanRepairRequest) -> dict[str, Any]:
    metadata = dict(plan.get("repairMetadata") or {})
    clarifications = list(metadata.get("confirmedClarifications") or [])
    for item in request.confirmed_clarifications:
        if isinstance(item, dict):
            clarifications.append(
                {
                    "topic": str(item.get("topic") or "preference"),
                    "value": str(item.get("value") or "")[:240],
                    "provenance": str(item.get("provenance") or "confirmed"),
                }
            )
    for delta in request.deltas:
        for answer in delta.confirmed_answers:
            if not isinstance(answer, dict):
                continue
            clarifications.append(
                {
                    "topic": str(answer.get("topic") or answer.get("need_id") or "preference"),
                    "value": str(answer.get("value") or "")[:240],
                    "provenance": str(answer.get("provenance") or "confirmed"),
                }
            )
    if clarifications:
        metadata["confirmedClarifications"] = clarifications[:12]
    assumptions = list(metadata.get("assumptionsCreated") or [])
    for delta in request.deltas:
        for assumption in delta.assumptions_created:
            if isinstance(assumption, dict):
                assumptions.append(
                    {
                        "kind": str(assumption.get("kind") or "user_preference"),
                        "provenance": str(assumption.get("provenance") or "confirmed"),
                        "confidence": assumption.get("confidence", 1.0),
                    }
                )
    if assumptions:
        metadata["assumptionsCreated"] = assumptions[:12]
    if metadata:
        plan["repairMetadata"] = metadata
    return plan


def deterministic_plan_repair(request: PlanRepairRequest) -> PlanRepairOutput:
    """Apply deterministic repair/regeneration without LLM involvement."""
    mode = choose_repair_mode(request)
    status = _status_for_mode(mode)
    plan_id = request.prior_plan.plan_id if request.prior_plan is not None else None

    if mode == "continue":
        return PlanRepairOutput(
            status=status,
            mode_used=mode,
            plan_id=plan_id,
            decision_summary="No meaningful delta — continue with the existing plan.",
            reason_codes=["no_meaningful_delta"],
            confidence=0.85,
            safe_to_use=False,
        )

    if mode == "abort_safely":
        return PlanRepairOutput(
            status=status,
            mode_used=mode,
            plan_id=plan_id,
            decision_summary="Unsafe output detected — abort safely without applying a repaired plan.",
            reason_codes=["unsafe_output_abort"],
            confidence=0.95,
            safe_to_use=False,
        )

    if mode == "clarify_first":
        return PlanRepairOutput(
            status=status,
            mode_used=mode,
            plan_id=plan_id,
            decision_summary="Missing preference context — clarify before repairing the plan.",
            reason_codes=["missing_preference_clarify_first"],
            confidence=0.7,
            safe_to_use=False,
        )

    if mode == "regenerate":
        new_plan_id = f"regenerated-{uuid.uuid4().hex[:10]}"
        return PlanRepairOutput(
            status=status,
            mode_used=mode,
            plan_id=new_plan_id,
            repaired_plan={
                "plan_id": new_plan_id,
                "user_goal": request.user_goal[:500],
                "execution_mode": "diagnostic_regeneration",
                "subtasks": [],
                "repairMetadata": {"regenerated": True, "priorPlanId": plan_id},
            },
            removed_subtask_ids=[str(item.get("id") or "") for item in (request.prior_plan.subtasks if request.prior_plan else [])],
            decision_summary="Goal drift detected — diagnostic regeneration requested.",
            reason_codes=["goal_drift_regenerate"],
            confidence=0.8,
            safe_to_use=False,
        )

    # repair mode
    prior_subtasks = list(request.prior_plan.subtasks if request.prior_plan is not None else [])
    affected = _affected_subtask_ids(request)
    if not affected and prior_subtasks:
        affected = {str(prior_subtasks[-1].get("id") or "")}

    preserved: list[str] = []
    revised: list[str] = []
    repaired_subtasks: list[dict[str, Any]] = []

    for subtask in prior_subtasks:
        subtask_id = str(subtask.get("id") or "")
        if not subtask_id:
            continue
        if subtask_id in affected:
            revised_subtask = copy.deepcopy(subtask)
            revised_subtask["status"] = "revised"
            revised_subtask["repairReason"] = "delta_affected"
            repaired_subtasks.append(revised_subtask)
            revised.append(subtask_id)
        else:
            repaired_subtasks.append(copy.deepcopy(subtask))
            preserved.append(subtask_id)

    repaired_plan: dict[str, Any] = {
        "plan_id": plan_id or f"repaired-{uuid.uuid4().hex[:10]}",
        "user_goal": request.user_goal[:500],
        "execution_mode": "diagnostic_repair",
        "subtasks": repaired_subtasks,
        "assumptions": list(request.prior_plan.assumptions if request.prior_plan else []),
    }
    repaired_plan = _merge_confirmed_clarifications(repaired_plan, request)

    reason_codes = ["deterministic_repair"]
    if any(delta.kind == "clarification_answered" for delta in request.deltas):
        reason_codes.append("clarification_answered_repair")
    if any(delta.kind == "assumption_violated" for delta in request.deltas):
        reason_codes.append("assumption_violated_repair")

    return PlanRepairOutput(
        status=status,
        mode_used=mode,
        plan_id=str(repaired_plan.get("plan_id")),
        repaired_plan=repaired_plan,
        preserved_subtask_ids=preserved,
        revised_subtask_ids=revised,
        added_subtask_ids=[],
        removed_subtask_ids=[],
        decision_summary="Deterministic warm repair preserved unaffected subtasks and revised invalidated parts.",
        reason_codes=reason_codes,
        confidence=0.75,
        safe_to_use=False,
    )
