"""Unit tests for plan delta builder (Phase 19)."""

from __future__ import annotations

from app.agent.planner.plan_delta import delta_from_clarification_resolution, deltas_from_monitor_diagnostics


def test_clarification_answered_creates_delta() -> None:
    delta = delta_from_clarification_resolution(
        clarification_state_metadata={"status": "confirmed", "clarificationId": "c-1"},
        confirmed_answers=[{"value": "prioritize mandatory requirements", "provenance": "confirmed"}],
        assumptions_created=[{"kind": "user_preference", "provenance": "confirmed"}],
    )
    assert delta is not None
    assert delta.kind == "clarification_answered"


def test_monitor_goal_drift_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics(
        {
            "signals": [{"kind": "goal_drift", "severity": "high"}],
            "decision": {"action": "request_plan_regeneration", "reason": "goal drift"},
        }
    )
    assert any(delta.kind == "goal_drift" for delta in deltas)


def test_assumption_violation_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "assumption_violation"}]})
    assert any(delta.kind == "assumption_violated" for delta in deltas)


def test_missing_context_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "missing_context"}]})
    assert any(delta.kind == "missing_context_unresolved" for delta in deltas)


def test_unsafe_output_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "unsafe_output"}]})
    assert any(delta.kind == "unsafe_output_detected" for delta in deltas)


def test_local_failure_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "local_execution_failure"}]})
    assert any(delta.kind == "subtask_failed" for delta in deltas)


def test_exhausted_path_creates_delta() -> None:
    deltas = deltas_from_monitor_diagnostics({"signals": [{"kind": "exhausted_path"}]})
    assert any(delta.kind == "exhausted_path" for delta in deltas)
    assert not any(delta.kind == "subtask_failed" for delta in deltas)


def test_malformed_diagnostics_never_raise() -> None:
    assert deltas_from_monitor_diagnostics({}) == []
    assert deltas_from_monitor_diagnostics({"signals": "bad"}) == []
    assert delta_from_clarification_resolution(
        clarification_state_metadata={},
        confirmed_answers=[],
    ) is None
