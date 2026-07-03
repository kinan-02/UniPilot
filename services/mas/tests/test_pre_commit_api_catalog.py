"""Tests for pre-commit validation with API Mongo catalog."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.validator.pre_commit import validate_plan_proposal


def test_validate_plan_proposal_uses_api_offered_catalog() -> None:
    engine = MagicMock()
    engine.course_catalog = {"00140008": {}}
    engine.evaluate_eligibility.return_value = (False, ["00940139"])

    user_context = {
        "api_semester_catalog": {
            "status": "ok",
            "offeredCourseNumbers": ["00140102"],
        },
        "api_suggested_course_numbers": ["00140102"],
    }

    ok, violations, references = validate_plan_proposal(
        course_ids=["00140102"],
        engine=engine,
        completed_courses=[],
        user_context=user_context,
    )

    assert ok is True
    assert violations == []
    assert "catalog:source=api_mongo" in references
    engine.evaluate_eligibility.assert_not_called()


def test_validate_plan_proposal_rejects_course_not_in_api_offerings() -> None:
    engine = MagicMock()
    engine.course_catalog = {"00140008": {}}

    user_context = {
        "api_semester_catalog": {
            "status": "ok",
            "offeredCourseNumbers": ["00140102"],
        }
    }

    ok, violations, _references = validate_plan_proposal(
        course_ids=["00140008"],
        engine=engine,
        completed_courses=[],
        user_context=user_context,
    )

    assert ok is False
    assert any("not offered" in message for message in violations)
