"""Unit tests for task planner."""

from app.agent.intent_router import classify_intent
from app.agent.task_planner import build_task_plan


def test_graduation_task_plan_is_read_only():
    classification = classify_intent("Check my graduation progress")
    plan = build_task_plan(classification)
    assert plan.workflow == "graduation_progress_workflow"
    assert plan.read_only is True


def test_transcript_import_requires_confirmation_path():
    classification = classify_intent("Import my transcript")
    plan = build_task_plan(classification)
    assert plan.workflow == "transcript_import_workflow"
    assert plan.read_only is False
