"""Assign stable attempt numbers when the same course appears multiple times."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, TypeVar

T = TypeVar("T")


def assign_sequential_course_attempts(
    rows: list[T],
    *,
    course_number: Callable[[T], str],
    semester_code: Callable[[T], str],
    attempt: Callable[[T], int],
    with_attempt: Callable[[T, int], T],
) -> list[T]:
    """Number retakes across semesters (and מועד ב within a semester) as attempt 1, 2, …"""
    grouped: dict[str, list[T]] = defaultdict(list)
    for row in rows:
        grouped[course_number(row)].append(row)

    assigned: list[T] = []
    for course in sorted(grouped):
        course_rows = sorted(
            grouped[course],
            key=lambda row: (semester_code(row), attempt(row)),
        )
        for index, row in enumerate(course_rows):
            resolved_attempt = max(attempt(row), index + 1)
            assigned.append(with_attempt(row, resolved_attempt))

    assigned.sort(key=lambda row: (semester_code(row), course_number(row), attempt(row)))
    return assigned
