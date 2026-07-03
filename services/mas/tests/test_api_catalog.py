"""Unit tests for API Mongo catalog helpers."""

from __future__ import annotations

from app.services.api_catalog import (
    api_offered_course_numbers,
    api_suggested_course_numbers,
    course_is_api_validated,
    is_course_in_active_catalog,
    uses_api_semester_catalog,
)


class _StubEngine:
    course_catalog = {"00140008": {}, "00940139": {}}


def test_uses_api_semester_catalog_when_payload_ok() -> None:
    context = {"api_semester_catalog": {"status": "ok", "offeredCourseNumbers": ["00140008"]}}
    assert uses_api_semester_catalog(context) is True


def test_api_offered_course_numbers_normalizes_values() -> None:
    context = {
        "api_semester_catalog": {
            "status": "ok",
            "offeredCourseNumbers": ["00140008", "940139"],
        }
    }
    assert api_offered_course_numbers(context) == {"00140008", "00940139"}


def test_api_suggested_course_numbers_from_planned_courses() -> None:
    context = {
        "api_semester_catalog": {
            "status": "ok",
            "plannedCourses": [
                {"courseNumber": "00140102", "credits": 3},
                {"courseNumber": "00940411", "credits": 3.5},
            ],
        }
    }
    assert api_suggested_course_numbers(context) == ["00140102", "00940411"]


def test_is_course_in_active_catalog_prefers_api_offerings() -> None:
    engine = _StubEngine()
    context = {
        "api_semester_catalog": {
            "status": "ok",
            "offeredCourseNumbers": ["00140102"],
        }
    }
    assert is_course_in_active_catalog(engine=engine, course_id="00140102", user_context=context)
    assert not is_course_in_active_catalog(engine=engine, course_id="00140008", user_context=context)


def test_course_is_api_validated() -> None:
    context = {"api_suggested_course_numbers": ["00140102"]}
    assert course_is_api_validated("00140102", context)
    assert not course_is_api_validated("00940411", context)
