"""Helpers for MAS planning against API Mongo semester catalog."""

from __future__ import annotations

from typing import Any


def _normalize_course_number(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(8) if digits else str(value).strip()


def uses_api_semester_catalog(user_context: dict[str, Any] | None) -> bool:
    if not isinstance(user_context, dict):
        return False
    catalog = user_context.get("api_semester_catalog")
    return isinstance(catalog, dict) and catalog.get("status") == "ok"


def api_offered_course_numbers(user_context: dict[str, Any] | None) -> set[str] | None:
    if not uses_api_semester_catalog(user_context):
        return None
    catalog = user_context.get("api_semester_catalog")
    if not isinstance(catalog, dict):
        return None
    numbers: set[str] = set()
    for raw in catalog.get("offeredCourseNumbers") or []:
        normalized = _normalize_course_number(str(raw))
        if normalized:
            numbers.add(normalized)
    return numbers or None


def api_suggested_course_numbers(user_context: dict[str, Any] | None) -> list[str]:
    if not isinstance(user_context, dict):
        return []
    explicit = user_context.get("api_suggested_course_numbers")
    if isinstance(explicit, list) and explicit:
        return [
            normalized
            for raw in explicit
            if (normalized := _normalize_course_number(str(raw)))
        ]

    catalog = user_context.get("api_semester_catalog")
    if not isinstance(catalog, dict):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for course in catalog.get("plannedCourses") or []:
        if not isinstance(course, dict):
            continue
        normalized = _normalize_course_number(
            str(course.get("courseNumber") or course.get("number") or "")
        )
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def api_course_credits_map(user_context: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(user_context, dict):
        return {}
    explicit = user_context.get("api_course_credits")
    if isinstance(explicit, dict) and explicit:
        credits: dict[str, float] = {}
        for key, value in explicit.items():
            normalized = _normalize_course_number(str(key))
            if not normalized:
                continue
            try:
                credits[normalized] = float(value)
            except (TypeError, ValueError):
                continue
        return credits

    catalog = user_context.get("api_semester_catalog")
    if not isinstance(catalog, dict):
        return {}
    credits = {}
    for course in catalog.get("plannedCourses") or []:
        if not isinstance(course, dict):
            continue
        normalized = _normalize_course_number(
            str(course.get("courseNumber") or course.get("number") or "")
        )
        if not normalized:
            continue
        raw_credits = course.get("credits")
        if raw_credits is None:
            continue
        try:
            credits[normalized] = float(raw_credits)
        except (TypeError, ValueError):
            continue
    return credits


def is_course_in_active_catalog(
    *,
    engine: Any,
    course_id: str,
    user_context: dict[str, Any] | None,
) -> bool:
    normalized = _normalize_course_number(course_id)
    if not normalized:
        return False
    offered = api_offered_course_numbers(user_context)
    if offered is not None:
        return normalized in offered

    catalog = getattr(engine, "course_catalog", {})
    if course_id in catalog or normalized in catalog:
        return True
    return any(_normalize_course_number(str(key)) == normalized for key in catalog)


def course_is_api_validated(
    course_id: str,
    user_context: dict[str, Any] | None,
) -> bool:
    normalized = _normalize_course_number(course_id)
    if not normalized:
        return False
    return normalized in set(api_suggested_course_numbers(user_context))
