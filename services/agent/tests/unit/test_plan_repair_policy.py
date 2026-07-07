"""Unit tests for plan repair policy (Phase 19)."""

from __future__ import annotations

from app.agent.planner.repair_policy import choose_repair_mode
from app.agent.planner.repair_schemas import PlanExecutionDelta, PlanRepairRequest


def _request(*deltas: PlanExecutionDelta) -> PlanRepairRequest:
    return PlanRepairRequest(request_id="req", user_goal="goal", deltas=list(deltas))


def _delta(kind: str, **kwargs) -> PlanExecutionDelta:
    return PlanExecutionDelta(
        delta_id=f"delta-{kind}",
        source="monitor",
        kind=kind,  # type: ignore[arg-type]
        summary=f"{kind} summary",
        **kwargs,
    )


def test_unsafe_output_chooses_abort_safely() -> None:
    assert choose_repair_mode(_request(_delta("unsafe_output_detected"))) == "abort_safely"


def test_goal_drift_chooses_regenerate() -> None:
    assert choose_repair_mode(_request(_delta("goal_drift"))) == "regenerate"


def test_clarification_answered_chooses_repair() -> None:
    assert choose_repair_mode(_request(_delta("clarification_answered"))) == "repair"


def test_assumption_violation_chooses_repair() -> None:
    assert choose_repair_mode(_request(_delta("assumption_violated"))) == "repair"


def test_preference_missing_context_chooses_clarify_first() -> None:
    delta = _delta("missing_context_unresolved", evidence={"ambiguityType": "preference"})
    assert choose_repair_mode(_request(delta)) == "clarify_first"


def test_epistemic_missing_context_chooses_repair() -> None:
    assert choose_repair_mode(_request(_delta("missing_context_unresolved"))) == "repair"


def test_subtask_failed_chooses_repair() -> None:
    assert choose_repair_mode(_request(_delta("subtask_failed"))) == "repair"


def test_exhausted_path_chooses_regenerate() -> None:
    assert choose_repair_mode(_request(_delta("exhausted_path"))) == "regenerate"


def test_no_delta_chooses_continue() -> None:
    assert choose_repair_mode(_request()) == "continue"
