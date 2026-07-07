"""Unit tests for replan cycle bounds (Phase 28.2)."""

from __future__ import annotations

from app.agent.planner.repair_schemas import PlanExecutionDelta
from app.agent.planner.replan_cycle_budget import (
    apply_replan_cycle_bounds,
    build_replan_cycle_budget,
    goal_fingerprint,
)


def _delta(kind: str) -> PlanExecutionDelta:
    return PlanExecutionDelta(
        delta_id=f"delta-{kind}",
        source="monitor",
        kind=kind,  # type: ignore[arg-type]
        summary=f"{kind} summary",
    )


def test_first_repair_attempt_allowed() -> None:
    budget = build_replan_cycle_budget(user_goal="Check graduation progress")
    decision = apply_replan_cycle_bounds(
        budget=budget,
        proposed_mode="repair",
        deltas=[_delta("subtask_failed")],
    )
    assert decision.effective_mode == "repair"
    assert not decision.bounded


def test_second_repair_attempt_allowed() -> None:
    budget = build_replan_cycle_budget(user_goal="Check graduation progress", max_repairs=2)
    decision = apply_replan_cycle_bounds(
        budget=budget,
        proposed_mode="repair",
        deltas=[_delta("subtask_failed"), _delta("validation_failed")],
    )
    assert decision.effective_mode == "repair"
    assert not decision.bounded


def test_attempt_beyond_max_triggers_escalation() -> None:
    budget = build_replan_cycle_budget(user_goal="Check graduation progress", max_repairs=2)
    decision = apply_replan_cycle_bounds(
        budget=budget,
        proposed_mode="repair",
        deltas=[_delta("subtask_failed"), _delta("validation_failed"), _delta("budget_exceeded")],
    )
    assert decision.effective_mode == "abort_safely"
    assert decision.bounded
    assert decision.budget.exhausted


def test_regeneration_attempts_bounded() -> None:
    budget = build_replan_cycle_budget(user_goal="Check graduation progress", max_regenerations=1)
    decision = apply_replan_cycle_bounds(
        budget=budget,
        proposed_mode="regenerate",
        deltas=[_delta("goal_drift"), _delta("exhausted_path")],
    )
    assert decision.effective_mode == "clarify_first"
    assert decision.escalation_action == "ask_clarification"
    assert decision.bounded


def test_different_goal_fingerprint_gets_separate_budget() -> None:
    assert goal_fingerprint("Plan courses") != goal_fingerprint("Check graduation progress")
