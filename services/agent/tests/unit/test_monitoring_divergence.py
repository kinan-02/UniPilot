"""Unit tests for monitoring divergence detection (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.divergence import detect_divergence
from app.agent.monitoring.expectations import expectations_from_planner_output
from app.agent.monitoring.schemas import MonitorInput, PlanAssumption


def _input(**overrides):
    base = {
        "plan_id": "p1",
        "user_goal": "What am I missing to graduate?",
        "planner_output": {
            "plan_id": "p1",
            "user_goal": "What am I missing to graduate?",
            "subtasks": [{"id": "s1", "depends_on": [], "risk_level": "medium"}],
        },
        "supervisor_output": {"status": "completed", "failed_subtasks": []},
        "subtask_records": [{"subtask_id": "s1", "status": "completed", "result_summary": {"confidence": 0.8}}],
        "latest_user_message": "What am I missing to graduate?",
    }
    base.update(overrides)
    return MonitorInput(**base)


def test_no_issues_returns_none_or_continue() -> None:
    signals = detect_divergence(_input(), [], expectations_from_planner_output(_input().planner_output))
    assert any(signal.kind == "none" for signal in signals)


def test_failed_independent_subtask_returns_local_execution_failure() -> None:
    monitor_input = _input(
        subtask_records=[{"subtask_id": "s1", "status": "failed", "result_summary": {}}],
        supervisor_output={"status": "completed_with_warnings", "failed_subtasks": ["s1"]},
    )
    signals = detect_divergence(monitor_input, [], expectations_from_planner_output(monitor_input.planner_output))
    assert any(signal.kind == "local_execution_failure" for signal in signals)


def test_failed_required_dependency_returns_local_execution_failure_with_affected_subtasks() -> None:
    monitor_input = _input(
        planner_output={
            "plan_id": "p1",
            "user_goal": "Goal",
            "subtasks": [{"id": "s2", "depends_on": ["s1"], "risk_level": "medium"}],
        },
        subtask_records=[{"subtask_id": "s2", "status": "failed", "result_summary": {}}],
    )
    signals = detect_divergence(monitor_input, [], expectations_from_planner_output(monitor_input.planner_output))
    assert any("s2" in signal.related_subtask_ids for signal in signals if signal.kind == "local_execution_failure")


def test_assumption_contradiction_returns_assumption_violation() -> None:
    assumption = PlanAssumption(
        id="ctx1",
        kind="context_availability",
        statement="Context available",
        provenance="assumed",
        invalidation_signals=["context_still_missing"],
        consequence_if_wrong="high",
    )
    monitor_input = _input(
        planner_output={
            "plan_id": "p1",
            "user_goal": "Goal",
            "missing_context": ["transcript_summary"],
            "subtasks": [{"id": "s1"}],
        },
        supervisor_output={"status": "completed", "failed_subtasks": ["s1"]},
    )
    signals = detect_divergence(monitor_input, [assumption], [])
    assert any(signal.kind == "assumption_violation" for signal in signals)


def test_goal_drift_signal_returns_goal_drift() -> None:
    monitor_input = _input(
        latest_user_message="Compare two semester plans instead",
        task_understanding={"normalized_request": "Compare semester plans", "primary_intent": "semester_planning"},
        planner_output={
            "plan_id": "p1",
            "user_goal": "What am I missing to graduate?",
            "primary_intent": "graduation_progress_check",
            "subtasks": [{"id": "s1"}],
        },
    )
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "goal_drift" for signal in signals)


def test_supervisor_budget_exceeded_returns_budget_exceeded() -> None:
    monitor_input = _input(supervisor_output={"status": "budget_exceeded"})
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "budget_exceeded" for signal in signals)


def test_forbidden_payload_metadata_returns_unsafe_output() -> None:
    monitor_input = _input(
        validation_metadata={"issues": [{"code": "unsafe_output_detected", "severity": "error"}]},
    )
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "unsafe_output" for signal in signals)


def test_proposed_action_detected_returns_unsafe_output() -> None:
    monitor_input = _input(
        subtask_records=[{"subtask_id": "s1", "status": "completed", "result_summary": {"hasProposedActions": True}}],
    )
    signals = detect_divergence(monitor_input, [], expectations_from_planner_output(monitor_input.planner_output))
    assert any(signal.kind == "unsafe_output" for signal in signals)


def test_missing_context_returns_missing_context() -> None:
    monitor_input = _input(planner_output={"plan_id": "p1", "user_goal": "Goal", "missing_context": ["profile preference"], "subtasks": [{"id": "s1"}]})
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "missing_context" for signal in signals)


def test_validation_failed_returns_validation_failure() -> None:
    monitor_input = _input(validation_metadata={"status": "failed", "safeMatch": False, "issues": []})
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "validation_failure" for signal in signals)


def test_promotion_blocked_is_informational_unless_repeated_critical() -> None:
    monitor_input = _input(promotion_metadata={"promoted": False, "status": "blocked", "reasons": [{"code": "not_eligible"}]})
    signals = detect_divergence(monitor_input, [], [])
    assert any(signal.kind == "promotion_blocked" for signal in signals)
