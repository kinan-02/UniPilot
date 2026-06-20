"""Resolve catalog prerequisites for semester planning."""

from __future__ import annotations

import re
from typing import Any

COURSE_NUMBER_PATTERN = re.compile(r"\b0\d{7}\b")


def extract_course_numbers_from_text(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(COURSE_NUMBER_PATTERN.findall(str(text))))


def resolve_prerequisite_ids(
    course: dict[str, Any],
    *,
    courses_by_number: dict[str, dict[str, Any]],
) -> list[Any]:
    explicit = course.get("prerequisites")
    if explicit:
        return list(explicit)

    numbers = extract_course_numbers_from_text(course.get("prerequisitesText"))
    resolved: list[Any] = []
    for number in numbers:
        match = courses_by_number.get(number)
        if match and match.get("_id") is not None:
            resolved.append(match["_id"])
    return resolved


def build_courses_by_number(catalog_courses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for course in catalog_courses:
        number = course.get("courseNumber") or course.get("number")
        if number is not None:
            indexed[str(number)] = course
    return indexed
