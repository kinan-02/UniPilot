"""Plan semester codes (YYYY-1/2/3) ↔ Technion offering keys (academicYear + 200/201/202)."""

from __future__ import annotations

import re
from typing import Any

PLAN_SEMESTER_PATTERN = re.compile(r"^(\d{4})-([123])$")


def plan_semester_to_offering_keys(semester_code: str) -> tuple[int, int] | None:
    """Map plan code like 2025-2 to offering academicYear=2025, semesterCode=201."""
    match = PLAN_SEMESTER_PATTERN.match(str(semester_code).strip())
    if not match:
        return None
    academic_year = int(match.group(1))
    term_index = int(match.group(2))
    return academic_year, 200 + term_index - 1


def pick_best_offering(
    offerings: list[dict[str, Any]],
    *,
    preferred_academic_year: int,
    semester_code: int,
) -> dict[str, Any] | None:
    """Choose an offering for the term, preferring exact year then nearest catalog year."""
    same_term = [
        offering
        for offering in offerings
        if int(offering.get("semesterCode") or 0) == semester_code
    ]
    if not same_term:
        return None

    exact = next(
        (
            offering
            for offering in same_term
            if int(offering.get("academicYear") or 0) == preferred_academic_year
        ),
        None,
    )
    if exact:
        return exact

    return min(
        same_term,
        key=lambda offering: abs(int(offering.get("academicYear") or 0) - preferred_academic_year),
    )
