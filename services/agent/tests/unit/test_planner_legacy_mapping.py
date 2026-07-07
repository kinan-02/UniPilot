"""Unit tests for the Phase 5 legacy workflow -> capability name mapping."""

from __future__ import annotations

from app.agent.planner.legacy_mapping import (
    build_legacy_workflow_plan_summary,
    legacy_workflow_to_capability_name,
)

_KNOWN_WORKFLOWS = [
    "graduation_progress_workflow",
    "course_question_workflow",
    "transcript_import_workflow",
    "semester_planning_workflow",
    "requirement_explanation_workflow",
    "general_academic_workflow",
]


def test_known_workflows_map_to_identical_capability_name() -> None:
    for workflow_name in _KNOWN_WORKFLOWS:
        assert legacy_workflow_to_capability_name(workflow_name) == workflow_name


def test_unknown_workflow_falls_back_to_general_academic_workflow() -> None:
    assert legacy_workflow_to_capability_name("totally_made_up_workflow") == "general_academic_workflow"


def test_none_or_empty_workflow_falls_back_to_general_academic_workflow() -> None:
    assert legacy_workflow_to_capability_name(None) == "general_academic_workflow"
    assert legacy_workflow_to_capability_name("") == "general_academic_workflow"


def test_build_legacy_workflow_plan_summary_shape() -> None:
    summary = build_legacy_workflow_plan_summary(
        workflow_name="course_question_workflow",
        read_only=True,
        requires_confirmation=False,
        primary_intent="course_question",
    )
    assert summary == {
        "workflow": "course_question_workflow",
        "capability_name": "course_question_workflow",
        "read_only": True,
        "requires_confirmation": False,
        "primary_intent": "course_question",
    }


def test_build_legacy_workflow_plan_summary_uses_mapping_for_capability_name() -> None:
    summary = build_legacy_workflow_plan_summary(
        workflow_name="unmapped_workflow",
        read_only=False,
        requires_confirmation=True,
        primary_intent="transcript_import",
    )
    assert summary["capability_name"] == "general_academic_workflow"
    assert summary["requires_confirmation"] is True
