"""Resolve effective completed course numbers from Mongo transcript rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

PASSING_GRADE_THRESHOLD = 55


def course_number_from_catalog_document(course: dict[str, Any]) -> str | None:
    """Match API catalog field naming (`courseNumber` primary, `number` legacy)."""
    number = course.get("courseNumber") or course.get("number")
    if number is None:
        return None
    normalized = str(number).strip()
    return normalized or None


def _parse_numeric_grade(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if numeric < 0 or numeric > 100:
        return None
    return numeric


def _is_passing_record(record: dict[str, Any]) -> bool:
    grade = _parse_numeric_grade(record.get("grade"))
    if grade is not None:
        return grade >= PASSING_GRADE_THRESHOLD
    points = _parse_numeric_grade(record.get("gradePoints"))
    if points is not None:
        return points >= PASSING_GRADE_THRESHOLD
    return False


def _recorded_at_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _semester_code_rank(semester_code: str = "") -> tuple[int, int]:
    raw = str(semester_code or "").strip()
    parts = raw.split("-", 1)
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in {"1", "2", "3"}:
        return (0, 0)
    return (int(parts[0]), int(parts[1]))


def _latest_attempt_rank(record: dict[str, Any]) -> tuple[int, int, int, float]:
    year, term = _semester_code_rank(str(record.get("semesterCode") or ""))
    return (
        year,
        term,
        max(1, int(record.get("attempt") or 1)),
        _recorded_at_timestamp(record.get("recordedAt")),
    )


def extract_effective_completed_course_numbers(
    completed_records: list[dict[str, Any]],
    *,
    number_by_course_id: dict[str, str],
) -> list[str]:
    """
    Latest passing attempt per course, mapped to catalog course numbers.

    Mirrors API graduation progress transcript handling so MAS sees the same
    completions the web app and graduation endpoint use.
    """
    latest_by_course_id: dict[str, dict[str, Any]] = {}
    latest_rank_by_course_id: dict[str, tuple[int, int, int, float]] = {}

    for record in completed_records:
        course_id = record.get("courseId")
        if course_id is None:
            continue
        course_key = str(course_id)
        rank = _latest_attempt_rank(record)
        existing_rank = latest_rank_by_course_id.get(course_key)
        if existing_rank is not None and rank <= existing_rank:
            continue
        latest_rank_by_course_id[course_key] = rank
        latest_by_course_id[course_key] = record

    numbers: list[str] = []
    seen: set[str] = set()
    for course_key, record in latest_by_course_id.items():
        if not _is_passing_record(record):
            continue
        number = number_by_course_id.get(course_key)
        if not number or number in seen:
            continue
        seen.add(number)
        numbers.append(number)

    return sorted(numbers)
