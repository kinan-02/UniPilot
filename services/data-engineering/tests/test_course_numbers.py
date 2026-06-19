"""Tests for Technion course-number normalization."""

import pytest

from app.utils.course_numbers import extract_course_title_pairs, normalize_course_number


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0940700", "00940700"),
        ("09407000", "00940700"),
        ("1040031", "01040031"),
        ("01040031", "01040031"),
        ("00940139", "00940139"),
        ("3 0980413", "00980413"),
        ("0960412", "00960412"),
    ],
)
def test_normalize_course_number(raw: str, expected: str) -> None:
    assert normalize_course_number(raw) == expected


def test_normalize_course_number_rejects_garbage() -> None:
    assert normalize_course_number("abc") is None
    assert normalize_course_number("") is None


def test_extract_course_title_pairs_from_inline_text() -> None:
    text = "0940345 מתמטיקה דיסקרטית 3.5 נק'  0941310 אלגברה לינארית"
    pairs = extract_course_title_pairs(text)
    numbers = {item["courseNumber"] for item in pairs}
    assert "00940345" in numbers
    assert "00941310" in numbers
