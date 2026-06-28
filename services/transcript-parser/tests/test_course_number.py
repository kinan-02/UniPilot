"""Tests for course number normalization."""

from app.services.course_number import normalize_course_number


def test_normalize_course_number_left_pads_seven_digit_values():
    assert normalize_course_number("960401") == "00960401"


def test_normalize_course_number_preserves_canonical_value():
    assert normalize_course_number("00960401") == "00960401"


def test_normalize_course_number_rejects_invalid_values():
    assert normalize_course_number("12345") is None
    assert normalize_course_number("123456789") is None
