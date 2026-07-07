"""Unit tests for plan snapshot builder (Phase 19)."""

from __future__ import annotations

from app.agent.planner.plan_snapshot import (
    build_fallback_plan_snapshot,
    build_plan_snapshot_from_planner_output,
    snapshot_omits_raw_payloads,
)


def _planner_output() -> dict:
    return {
        "plan_id": "plan-abc",
        "user_goal": "What am I missing to graduate?",
        "subtasks": [
            {
                "id": "ask_specialist",
                "title": "Ask graduation specialist",
                "kind": "analyze",
                "capability_name": "graduation_progress_agent",
                "objective": "Determine remaining requirements.",
                "success_criteria": ["Use deterministic graduation engine."],
                "compiled_context": {"must": "not appear"},
            }
        ],
        "assumptions": ["Student wants graduation guidance"],
        "validation_strategy": ["Preserve deterministic workflow output."],
        "prompt": "must not appear",
    }


def test_builds_snapshot_from_planner_output() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    assert snapshot.plan_id == "plan-abc"


def test_preserves_compact_subtasks() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    assert snapshot.subtasks[0]["id"] == "ask_specialist"
    assert "compiled_context" not in snapshot.subtasks[0]


def test_preserves_assumptions() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    assert snapshot.assumptions[0]["statement"] == "Student wants graduation guidance"


def test_preserves_success_criteria() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    assert "Use deterministic graduation engine." in snapshot.success_criteria


def test_malformed_planner_output_returns_none_safely() -> None:
    assert build_plan_snapshot_from_planner_output({}) is None
    assert build_plan_snapshot_from_planner_output({"plan_id": ""}) is None


def test_raw_context_is_omitted() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    assert snapshot_omits_raw_payloads(snapshot)


def test_raw_prompt_is_omitted() -> None:
    snapshot = build_plan_snapshot_from_planner_output(_planner_output())
    assert snapshot is not None
    dumped = snapshot.model_dump()
    assert "prompt" not in dumped


def test_fallback_snapshot() -> None:
    snapshot = build_fallback_plan_snapshot(
        user_goal="Plan next semester",
        workflow_name="semester_planning_workflow",
        intent="semester_planning",
    )
    assert snapshot.source == "fallback"
    assert snapshot.subtasks
