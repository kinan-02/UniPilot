"""Unit tests for rules-first intent router."""

from app.agent.intent_router import classify_intent


def test_classify_graduation_progress_intent():
    result = classify_intent("What am I missing to graduate?")
    assert result.intent == "graduation_progress_check"
    assert result.confidence >= 0.8


def test_classify_course_question_with_number():
    result = classify_intent("Can I take 234218 next semester?")
    assert result.intent == "course_question"


def test_classify_course_question_without_number():
    result = classify_intent("Can I take this course next semester?")
    assert result.intent == "course_question"


def test_classify_semester_plan_generation():
    result = classify_intent("Build me a plan with no Friday classes")
    assert result.intent == "semester_plan_generation"


def test_classify_semester_plan_modification():
    result = classify_intent("Make this plan lighter")
    assert result.intent == "semester_plan_modification"


def test_classify_requirement_explanation_incomplete():
    result = classify_intent("Why is this requirement incomplete?")
    assert result.intent == "requirement_explanation"


def test_classify_transcript_import():
    result = classify_intent("Import my transcript PDF")
    assert result.intent == "transcript_import"
    assert result.requires_file is True


def test_classify_empty_message():
    result = classify_intent("   ")
    assert result.intent == "unknown_or_unsupported"
