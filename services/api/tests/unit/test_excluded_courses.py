"""Unit tests for vault-excluded catalog course numbers."""

from __future__ import annotations

from app.catalog.excluded_courses import (
    EXCLUDED_COURSE,
    is_production_excluded_course_number,
)


def test_excluded_course_constant_is_blocked() -> None:
    assert is_production_excluded_course_number(EXCLUDED_COURSE) is True


def test_non_excluded_course_is_allowed() -> None:
    assert is_production_excluded_course_number("00940345") is False


def test_empty_course_number_is_not_excluded() -> None:
    assert is_production_excluded_course_number(None) is False
    assert is_production_excluded_course_number("") is False
