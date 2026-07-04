"""Unit tests for advisor async offload classifier."""

from __future__ import annotations

from app.services.advisor_async_classifier import classify_advisor_offload
from app.services.advisor_ask_orchestrator import should_enqueue_advisor_job


def test_classify_planning_question_en():
    offload, reason = classify_advisor_offload("What should I take next semester to stay on track?")
    assert offload is True
    assert reason == "planning_intent"


def test_classify_graduation_question_he():
    offload, reason = classify_advisor_offload("עוד כמה נקודות זכות חסרות לי לסיים את התואר?")
    assert offload is True
    assert reason == "graduation_intent"


def test_classify_simple_syllabus_question_stays_sync():
    offload, reason = classify_advisor_offload("What is the syllabus for course 00440148?")
    assert offload is False
    assert reason is None


def test_classify_long_question_offloads():
    question = "Please review my situation. " + ("detail " * 60)
    offload, reason = classify_advisor_offload(question)
    assert offload is True
    assert reason == "long_question"


def test_execution_mode_sync_overrides_heavy_question():
    enqueue, reason = should_enqueue_advisor_job(
        "Build a spring plan that keeps me on track and flags risks.",
        "sync",
    )
    assert enqueue is False
    assert reason is None


def test_execution_mode_async_always_enqueues():
    enqueue, reason = should_enqueue_advisor_job("What is the syllabus?", "async")
    assert enqueue is True
    assert reason == "force_async"
