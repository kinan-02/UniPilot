"""Unit tests for deterministic prerequisite validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.schemas import AgentContextPack, ContextValidation
from app.services.course_question_service import analyze_course_question
from app.services.prerequisite_validation_service import (
    ELIGIBILITY_VALIDATION_SOURCE,
    PrerequisiteValidationResult,
    compose_eligibility_answer,
    extract_completed_course_codes_from_context,
    validate_course_prerequisites,
)


def _wiki_record(*, course: str, prerequisites: list[str], source: str = "wiki/courses/x.md") -> dict:
    return {
        "courseNumber": course,
        "sourcePath": source,
        "prerequisites": [{"courseNumber": code} for code in prerequisites],
    }


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_empty_completed_courses_with_prerequisites_not_eligible(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    result = validate_course_prerequisites(
        "02360343",
        completed_course_codes=[],
        completed_data_available=True,
    )
    assert result.eligibility_status == "not_eligible"
    assert result.eligibility_status != "eligible"
    assert result.missing_prerequisite_codes == ["02340129", "02340247"]


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_one_of_two_prerequisites_completed(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    result = validate_course_prerequisites(
        "02360343",
        completed_course_codes=["02340129"],
        completed_data_available=True,
    )
    assert result.eligibility_status == "not_eligible"
    assert result.satisfied_prerequisite_codes == ["02340129"]
    assert result.missing_prerequisite_codes == ["02340247"]


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_all_prerequisites_completed(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    result = validate_course_prerequisites(
        "02360343",
        completed_course_codes=["02340129", "02340247"],
        completed_data_available=True,
    )
    assert result.eligibility_status == "eligible"


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_no_prerequisites_eligible(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(course="00999999", prerequisites=[])
    result = validate_course_prerequisites(
        "00999999",
        completed_course_codes=[],
        completed_data_available=True,
    )
    assert result.eligibility_status == "eligible"
    assert result.has_prerequisites is False


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_completed_data_unavailable_is_unknown(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    result = validate_course_prerequisites(
        "02360343",
        completed_course_codes=[],
        completed_data_available=False,
    )
    assert result.eligibility_status == "unknown"
    assert result.eligibility_status != "eligible"


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_eligibility_answer_missing_prereqs_never_says_yes(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    validation = validate_course_prerequisites(
        "02360343",
        completed_course_codes=[],
        completed_data_available=True,
    )
    headline, verdict = compose_eligibility_answer(validation)
    assert verdict == "no"
    assert "yes — you appear eligible" not in headline.lower()


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_eligibility_answer_satisfied_may_say_eligible(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    validation = validate_course_prerequisites(
        "02360343",
        completed_course_codes=["02340129", "02340247"],
        completed_data_available=True,
    )
    headline, verdict = compose_eligibility_answer(validation)
    assert verdict == "yes"
    assert "eligible" in headline.lower()


def test_extract_completed_courses_from_user_context() -> None:
    codes, available = extract_completed_course_codes_from_context(
        user_context={"completedCourses": ["02340129"]},
    )
    assert available is True
    assert "02340129" in codes


@patch("app.services.prerequisite_validation_service.course_by_code")
def test_analyze_eligibility_uses_validation_not_stale_prereq_result(mock_course_by_code) -> None:
    mock_course_by_code.return_value = _wiki_record(
        course="02360343",
        prerequisites=["02340129", "02340247"],
    )
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "02360343"},
        user_context={"completedCourses": []},
        academic_context={
            "course": {"courseNumber": "02360343", "title": "Theory of Computation"},
            "prerequisiteResult": {"eligible": True, "missingPrerequisites": []},
        },
        validation=ContextValidation(status="valid"),
    )
    analysis = analyze_course_question(
        context=context,
        user_message="Can I take 02360343?",
    )
    assert analysis.focus == "eligibility"
    assert analysis.use_eligibility_validation is True
    assert analysis.verdict == "no"
    assert "yes — you appear eligible" not in analysis.headline.lower()
    assert "02340129" in analysis.headline
    assert "02340247" in analysis.headline


def test_llm_rewrite_skip_marker_constant() -> None:
    assert "Deterministic prerequisite eligibility validation" == ELIGIBILITY_VALIDATION_SOURCE
