"""Normalize imported transcript rows before persistence."""

from __future__ import annotations

from typing import Any


def resolve_import_credits(row, catalog_course: dict[str, Any] | None) -> float:
    """Prefer parsed PDF credits; fill from catalog only for graded rows missing credits."""
    parsed = float(row.creditsEarned)
    if parsed > 0:
        return parsed

    grade = float(row.grade)
    if grade == 0:
        return 0.0

    if catalog_course:
        catalog_credits = catalog_course.get("credits")
        if catalog_credits is not None and float(catalog_credits) > 0:
            return float(catalog_credits)

    return parsed


def resolve_import_grade_points(row) -> float | None:
    """Explicit grade points for exemptions and pass rows that should not use raw grade 0."""
    grade = float(row.grade)
    if grade == 0:
        return 0.0
    return None
