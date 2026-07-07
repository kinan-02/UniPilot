"""Unit tests for monitoring expectation extraction (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.expectations import expectations_from_planner_output, expectations_from_supervisor_plan


def _planner(**overrides):
    base = {
        "plan_id": "p1",
        "subtasks": [
            {
                "id": "s1",
                "capability_name": "graduation_progress_agent",
                "success_criteria": ["Report remaining credits"],
                "validation_requirements": ["No invented requirements"],
                "risk_level": "high",
            }
        ],
    }
    base.update(overrides)
    return base


def test_default_no_proposed_actions_expectation_generated() -> None:
    expectations = expectations_from_planner_output(_planner())
    assert any(item.kind == "no_proposed_actions" for item in expectations)


def test_default_no_writes_expectation_generated() -> None:
    expectations = expectations_from_planner_output(_planner())
    assert any(item.kind == "no_writes" for item in expectations)


def test_success_criteria_become_expectations() -> None:
    expectations = expectations_from_planner_output(_planner())
    assert any("Success criterion" in item.description for item in expectations)


def test_validation_requirements_become_expectations() -> None:
    expectations = expectations_from_planner_output(_planner())
    assert any("Validation requirement" in item.description for item in expectations)


def test_high_risk_subtasks_get_confidence_expectation() -> None:
    expectations = expectations_from_planner_output(_planner())
    assert any(item.kind == "confidence_threshold" for item in expectations)


def test_malformed_planner_output_never_raises() -> None:
    assert expectations_from_supervisor_plan(None) == []
    assert expectations_from_supervisor_plan({"subtasks": "bad"}) == []
