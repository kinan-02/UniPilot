"""Unit tests for transcript -> completed course number resolution."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.completed_course_transcript import (
    course_number_from_catalog_document,
    extract_effective_completed_course_numbers,
)


def test_course_number_from_catalog_document_prefers_course_number() -> None:
    assert course_number_from_catalog_document({"courseNumber": "00940139"}) == "00940139"
    assert course_number_from_catalog_document({"number": "00140008"}) == "00140008"
    assert course_number_from_catalog_document({"courseNumber": "00940139", "number": "00140008"}) == "00940139"


def test_extract_effective_completed_course_numbers_uses_latest_passing_attempt() -> None:
    course_id = "abc123"
    numbers = extract_effective_completed_course_numbers(
        [
            {
                "courseId": course_id,
                "grade": 40,
                "attempt": 1,
                "semesterCode": "2024-1",
            },
            {
                "courseId": course_id,
                "grade": 82,
                "attempt": 2,
                "semesterCode": "2025-1",
            },
        ],
        number_by_course_id={course_id: "00940139"},
    )
    assert numbers == ["00940139"]


def test_extract_effective_completed_course_numbers_ignores_failed_latest_attempt() -> None:
    course_id = "abc123"
    numbers = extract_effective_completed_course_numbers(
        [
            {
                "courseId": course_id,
                "grade": 82,
                "attempt": 1,
                "semesterCode": "2024-1",
            },
            {
                "courseId": course_id,
                "grade": 40,
                "attempt": 2,
                "semesterCode": "2025-1",
            },
        ],
        number_by_course_id={course_id: "00940139"},
    )
    assert numbers == []


def test_extract_effective_completed_course_numbers_deduplicates() -> None:
    numbers = extract_effective_completed_course_numbers(
        [
            {
                "courseId": "a",
                "grade": 90,
                "attempt": 1,
                "recordedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
            },
            {
                "courseId": "b",
                "grade": 88,
                "attempt": 1,
                "recordedAt": datetime(2025, 1, 2, tzinfo=timezone.utc),
            },
        ],
        number_by_course_id={"a": "00940139", "b": "00940139"},
    )
    assert numbers == ["00940139"]
