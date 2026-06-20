"""Technion numeric grade evaluation (0–100 scale; pass strictly above 55)."""

from __future__ import annotations

from typing import Any

PASSING_GRADE_THRESHOLD = 55


def parse_numeric_grade(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
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


def resolve_record_numeric_grade(record: dict[str, Any]) -> float | None:
    """Prefer explicit gradePoints; fall back to numeric grade field."""
    points = parse_numeric_grade(record.get("gradePoints"))
    if points is not None:
        return points
    return parse_numeric_grade(record.get("grade"))


def is_passing_numeric_grade(numeric_grade: float) -> bool:
    return numeric_grade > PASSING_GRADE_THRESHOLD


def is_passing_grade(record: dict[str, Any] | Any, grade_points: Any = None) -> bool:
    """Return True when the student passed (score strictly greater than 55)."""
    if isinstance(record, dict):
        numeric = resolve_record_numeric_grade(record)
    else:
        numeric = parse_numeric_grade(grade_points)
        if numeric is None:
            numeric = parse_numeric_grade(record)

    if numeric is None:
        return False
    return is_passing_numeric_grade(numeric)
