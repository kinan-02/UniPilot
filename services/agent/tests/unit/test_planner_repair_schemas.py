"""Unit tests for planner repair schemas (Phase 19)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.planner.repair_schemas import (
    PlanExecutionDelta,
    PlanRepairOutput,
    PlanRepairRequest,
    PlanSnapshot,
)


def test_plan_snapshot_parses() -> None:
    snapshot = PlanSnapshot(plan_id="plan-1", user_goal="Check graduation progress")
    assert snapshot.plan_id == "plan-1"
    assert snapshot.planner_mode == "cold"


def test_plan_execution_delta_parses() -> None:
    delta = PlanExecutionDelta(
        delta_id="delta-1",
        source="monitor",
        kind="goal_drift",
        summary="Goal changed",
    )
    assert delta.kind == "goal_drift"


def test_plan_repair_request_parses() -> None:
    request = PlanRepairRequest(request_id="req-1", user_goal="Plan courses")
    assert request.dry_run is True


def test_plan_repair_output_parses() -> None:
    output = PlanRepairOutput(
        status="repaired",
        mode_used="repair",
        decision_summary="Repaired affected subtasks.",
        safe_to_use=False,
    )
    assert output.safe_to_use is False


def test_defaults_are_safe() -> None:
    request = PlanRepairRequest(request_id="req-safe", user_goal="goal")
    output = PlanRepairOutput(status="skipped", mode_used="continue", decision_summary="skipped")
    assert request.dry_run is True
    assert output.safe_to_use is False
    assert output.confidence == 0.0


def test_forbidden_chain_of_thought_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanRepairOutput.model_validate(
            {
                "status": "failed",
                "mode_used": "continue",
                "decision_summary": "bad",
                "chain_of_thought": "secret",
            }
        )
