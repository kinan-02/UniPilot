"""Unit tests for monitoring schemas (Phase 16)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.monitoring.schemas import (
    DivergenceSignal,
    MonitorInput,
    MonitorOutput,
    PlanAssumption,
    ReplanDecision,
    SubtaskExpectation,
)


def test_plan_assumption_parses() -> None:
    assumption = PlanAssumption(
        id="a1",
        kind="user_preference",
        statement="Prefers lighter workload",
        provenance="assumed",
    )
    assert assumption.provenance == "assumed"


def test_subtask_expectation_parses() -> None:
    expectation = SubtaskExpectation(
        id="e1",
        subtask_id="s1",
        kind="no_proposed_actions",
        description="No actions",
    )
    assert expectation.kind == "no_proposed_actions"


def test_divergence_signal_parses() -> None:
    signal = DivergenceSignal(kind="missing_context", severity="warning", message="missing")
    assert signal.kind == "missing_context"


def test_replan_decision_parses() -> None:
    decision = ReplanDecision(action="continue", reason="ok")
    assert decision.repair_scope == "none"


def test_monitor_output_parses() -> None:
    output = MonitorOutput(
        status="passed",
        decision=ReplanDecision(action="continue", reason="ok"),
    )
    assert output.status == "passed"


def test_defaults_are_safe() -> None:
    decision = ReplanDecision(action="continue", reason="ok")
    assert decision.clarification_needed is False
    assert decision.repair_scope == "none"


def test_forbidden_chain_of_thought_fields_are_absent() -> None:
    with pytest.raises(ValidationError):
        MonitorInput.model_validate({"chain_of_thought": "secret"})
