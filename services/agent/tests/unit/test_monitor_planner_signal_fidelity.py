"""Unit tests for monitor→planner signal fidelity (Phase 28.2)."""

from __future__ import annotations

from app.agent.planner.plan_delta import deltas_from_monitor_diagnostics
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


def test_exhausted_path_divergence_becomes_exhausted_path_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "exhausted_path", "severity": "warning"}]})
    assert any(delta.kind == "exhausted_path" for delta in deltas)
    assert not any(delta.kind == "subtask_failed" for delta in deltas)


def test_ordinary_subtask_failure_remains_subtask_failed() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "local_execution_failure", "severity": "warning"}]})
    assert any(delta.kind == "subtask_failed" for delta in deltas)
    assert not any(delta.kind == "exhausted_path" for delta in deltas)


def test_goal_drift_does_not_collapse_into_subtask_failed() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "goal_drift", "severity": "error"}]})
    assert any(delta.kind == "goal_drift" for delta in deltas)
    assert not any(delta.kind == "subtask_failed" for delta in deltas)


def test_assumption_violation_preserves_kind() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "assumption_violation", "severity": "warning"}]})
    assert any(delta.kind == "assumption_violated" for delta in deltas)


def test_repair_policy_distinguishes_exhausted_path_from_subtask_failed() -> None:
    assert choose_repair_mode(_request(_delta("subtask_failed"))) == "repair"
    assert choose_repair_mode(_request(_delta("exhausted_path"))) == "regenerate"


def test_central_assumption_violation_prefers_regeneration() -> None:
    localized = _delta("assumption_violated", consequence="medium")
    central = _delta("assumption_violated", consequence="high", affected_subtask_ids=["a", "b"])
    assert choose_repair_mode(_request(localized)) == "repair"
    assert choose_repair_mode(_request(central)) == "regenerate"


def test_monitor_decision_repair_with_exhausted_path_signal() -> None:
    deltas = deltas_from_monitor_diagnostics(
        {
            "signals": [],
            "decision": {"action": "request_plan_repair", "reason": "exhausted_path_detected"},
        }
    )
    assert any(delta.kind == "exhausted_path" for delta in deltas)
