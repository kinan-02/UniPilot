"""Unit tests for deterministic plan repair (Phase 19)."""

from __future__ import annotations

from app.agent.planner.repair_fallback import deterministic_plan_repair
from app.agent.planner.repair_schemas import PlanExecutionDelta, PlanRepairRequest, PlanSnapshot


def _request(*, mode_hint: str | None = None, deltas: list[PlanExecutionDelta] | None = None) -> PlanRepairRequest:
    prior = PlanSnapshot(
        plan_id="plan-1",
        user_goal="Plan next semester",
        subtasks=[
            {"id": "s1", "title": "Gather context", "kind": "analyze", "capability_name": "x", "objective": "o1"},
            {"id": "s2", "title": "Plan semester", "kind": "execute", "capability_name": "y", "objective": "o2"},
        ],
    )
    return PlanRepairRequest(
        request_id="req-1",
        prior_plan=prior,
        user_goal="Plan next semester",
        deltas=deltas or [],
        requested_mode=mode_hint,  # type: ignore[arg-type]
        confirmed_clarifications=[{"topic": "preference", "value": "mandatory first", "provenance": "confirmed"}],
    )


def test_continue_returns_continued() -> None:
    output = deterministic_plan_repair(_request(mode_hint="continue"))
    assert output.status == "continued"


def test_abort_safely_returns_aborted_safely() -> None:
    output = deterministic_plan_repair(_request(mode_hint="abort_safely"))
    assert output.status == "aborted_safely"


def test_clarify_first_returns_clarification_needed() -> None:
    output = deterministic_plan_repair(_request(mode_hint="clarify_first"))
    assert output.status == "clarification_needed"


def test_repair_preserves_unaffected_subtasks() -> None:
    deltas = [
        PlanExecutionDelta(
            delta_id="d1",
            source="monitor",
            kind="subtask_failed",
            summary="failed",
            affected_subtask_ids=["s2"],
        )
    ]
    output = deterministic_plan_repair(_request(mode_hint="repair", deltas=deltas))
    assert "s1" in output.preserved_subtask_ids


def test_repair_revises_affected_subtasks() -> None:
    deltas = [
        PlanExecutionDelta(
            delta_id="d1",
            source="monitor",
            kind="subtask_failed",
            summary="failed",
            affected_subtask_ids=["s2"],
        )
    ]
    output = deterministic_plan_repair(_request(mode_hint="repair", deltas=deltas))
    assert "s2" in output.revised_subtask_ids


def test_repair_adds_confirmed_clarification_metadata() -> None:
    deltas = [
        PlanExecutionDelta(
            delta_id="d1",
            source="clarification",
            kind="clarification_answered",
            summary="answered",
            confirmed_answers=[{"value": "mandatory first", "provenance": "confirmed"}],
        )
    ]
    output = deterministic_plan_repair(_request(mode_hint="repair", deltas=deltas))
    assert output.repaired_plan is not None
    metadata = output.repaired_plan.get("repairMetadata") or {}
    assert metadata.get("confirmedClarifications")


def test_regenerate_returns_safe_to_use_false() -> None:
    output = deterministic_plan_repair(_request(mode_hint="regenerate"))
    assert output.status == "regenerated"
    assert output.safe_to_use is False


def test_output_never_contains_proposed_actions() -> None:
    output = deterministic_plan_repair(_request(mode_hint="repair", deltas=[]))
    dumped = output.model_dump_json()
    assert "proposed_actions" not in dumped


def test_output_never_contains_raw_context() -> None:
    output = deterministic_plan_repair(_request(mode_hint="repair", deltas=[]))
    dumped = output.model_dump_json()
    assert "compiled_context" not in dumped
    assert "raw_context" not in dumped
