"""Unit tests for prerequisite resolver helpers."""

from __future__ import annotations

from app.planning.prerequisite_resolver import (
    build_courses_by_number,
    canonical_course_number,
    extract_course_numbers_from_text,
)


def test_canonical_course_number_rejects_invalid_lengths():
    assert canonical_course_number("") is None
    assert canonical_course_number("12345") is None


def test_extract_course_numbers_returns_empty_for_blank_text():
    assert extract_course_numbers_from_text(None) == []
    assert extract_course_numbers_from_text("") == []


def test_canonical_course_number_rejects_invalid_padded_value():
    assert canonical_course_number("12345678") is None


def test_build_courses_by_number_skips_documents_without_number():
    indexed = build_courses_by_number([{"title": "No number course"}])
    assert indexed == {}
