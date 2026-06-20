"""Unit tests for Technion numeric grade evaluation."""

import pytest

from app.services.grade_evaluation import (
    PASSING_GRADE_THRESHOLD,
    is_passing_grade,
    is_passing_numeric_grade,
    parse_numeric_grade,
    resolve_record_numeric_grade,
)


def test_passing_threshold_is_55():
    assert PASSING_GRADE_THRESHOLD == 55


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, False),
        (55, False),
        (55.1, True),
        (56, True),
        (82, True),
        (100, True),
    ],
)
def test_is_passing_numeric_grade_boundary(value, expected):
    assert is_passing_numeric_grade(value) is expected


@pytest.mark.parametrize(
    "grade,expected",
    [
        (82, True),
        (55, False),
        (56, True),
        ("82", True),
        ("55", False),
        ("A", None),
        ("", None),
        (-1, None),
        (101, None),
    ],
)
def test_parse_numeric_grade(grade, expected):
    result = parse_numeric_grade(grade)
    if expected is None:
        assert result is None
    else:
        assert result == float(grade if not isinstance(grade, str) else grade)


def test_is_passing_grade_uses_grade_field():
    assert is_passing_grade({"grade": 82}) is True
    assert is_passing_grade({"grade": 55}) is False
    assert is_passing_grade({"grade": 40}) is False


def test_is_passing_grade_prefers_grade_points():
    assert is_passing_grade({"grade": 40, "gradePoints": 82}) is True
    assert is_passing_grade({"grade": 82, "gradePoints": 50}) is False


def test_resolve_record_numeric_grade():
    assert resolve_record_numeric_grade({"grade": 70}) == 70.0
    assert resolve_record_numeric_grade({"gradePoints": 88}) == 88.0
