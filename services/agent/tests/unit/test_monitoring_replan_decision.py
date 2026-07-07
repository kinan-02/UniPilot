"""Unit tests for monitoring replan decision policy (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.replan_decision import decide_replan_action
from app.agent.monitoring.schemas import DivergenceSignal, MonitorInput


def _signal(kind: str, **kwargs):
    return DivergenceSignal(kind=kind, severity=kwargs.pop("severity", "warning"), message=kind, **kwargs)


def test_unsafe_output_beats_all() -> None:
    decision = decide_replan_action(
        [_signal("unsafe_output", severity="error"), _signal("goal_drift", severity="error")],
        MonitorInput(),
    )
    assert decision.action == "abort_safely"


def test_goal_drift_beats_assumption_violation() -> None:
    decision = decide_replan_action(
        [_signal("goal_drift", severity="error"), _signal("assumption_violation")],
        MonitorInput(),
    )
    assert decision.action == "request_plan_regeneration"


def test_assumption_violation_beats_local_failure() -> None:
    decision = decide_replan_action(
        [_signal("assumption_violation"), _signal("local_execution_failure")],
        MonitorInput(),
    )
    assert decision.action == "request_plan_repair"


def test_exhausted_path_requests_repair() -> None:
    decision = decide_replan_action([_signal("exhausted_path")], MonitorInput())
    assert decision.action == "request_plan_repair"


def test_missing_preference_ambiguity_asks_clarification() -> None:
    decision = decide_replan_action(
        [
            _signal(
                "missing_context",
                evidence={"preferenceAmbiguity": True, "retrievableEpistemic": False},
            )
        ],
        MonitorInput(),
    )
    assert decision.action == "ask_clarification"
    assert decision.clarification_needed is True


def test_missing_epistemic_context_requests_repair() -> None:
    decision = decide_replan_action(
        [_signal("missing_context", evidence={"preferenceAmbiguity": False, "retrievableEpistemic": True})],
        MonitorInput(),
    )
    assert decision.action == "request_plan_repair"


def test_local_failure_retries_or_substitutes() -> None:
    decision = decide_replan_action(
        [_signal("local_execution_failure", related_subtask_ids=["s1"])],
        MonitorInput(),
    )
    assert decision.action in {"local_retry", "local_substitute"}


def test_clean_state_continues() -> None:
    decision = decide_replan_action([_signal("none", severity="info")], MonitorInput())
    assert decision.action == "continue"
