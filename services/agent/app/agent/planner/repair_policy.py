"""Deterministic repair-mode policy (Phase 19)."""

from __future__ import annotations

from app.agent.planner.repair_schemas import PlanExecutionDelta, PlanRepairRequest, RepairMode


def _has_kind(deltas: list[PlanExecutionDelta], kind: str) -> bool:
    return any(delta.kind == kind for delta in deltas)


def _missing_context_deltas(deltas: list[PlanExecutionDelta]) -> list[PlanExecutionDelta]:
    return [delta for delta in deltas if delta.kind == "missing_context_unresolved"]


def _is_preference_ambiguity(delta: PlanExecutionDelta) -> bool:
    ambiguity = str(delta.evidence.get("ambiguityType") or delta.evidence.get("ambiguity_type") or "").lower()
    if ambiguity == "preference":
        return True
    summary = delta.summary.lower()
    return "preference" in summary or "priorit" in summary


def _assumption_violation_deltas(deltas: list[PlanExecutionDelta]) -> list[PlanExecutionDelta]:
    return [delta for delta in deltas if delta.kind == "assumption_violated"]


def _central_assumption_violation(delta: PlanExecutionDelta) -> bool:
    if delta.consequence == "high":
        return True
    if len(delta.affected_subtask_ids) > 1:
        return True
    evidence = delta.evidence if isinstance(delta.evidence, dict) else {}
    return bool(evidence.get("failedSubtasksStillPresent") or evidence.get("missingContextStillPresent"))


def choose_repair_mode(request: PlanRepairRequest) -> RepairMode:
    """Apply Phase 19 priority order. Deterministic — never calls LLM."""
    if request.requested_mode is not None:
        return request.requested_mode

    deltas = list(request.deltas)
    if not deltas:
        return "continue"

    if _has_kind(deltas, "unsafe_output_detected"):
        return "abort_safely"

    if _has_kind(deltas, "goal_drift") or _has_kind(deltas, "user_goal_changed"):
        return "regenerate"

    if _has_kind(deltas, "clarification_answered"):
        return "repair"

    assumption_violations = _assumption_violation_deltas(deltas)
    if assumption_violations:
        if any(_central_assumption_violation(delta) for delta in assumption_violations):
            return "regenerate"
        return "repair"

    if _has_kind(deltas, "exhausted_path"):
        return "regenerate"

    missing = _missing_context_deltas(deltas)
    if missing:
        if any(_is_preference_ambiguity(delta) for delta in missing):
            return "clarify_first"
        return "repair"

    if _has_kind(deltas, "subtask_failed") or _has_kind(deltas, "validation_failed"):
        return "repair"

    if _has_kind(deltas, "missing_context_resolved"):
        return "repair"

    if _has_kind(deltas, "budget_exceeded"):
        return "repair"

    return "continue"
