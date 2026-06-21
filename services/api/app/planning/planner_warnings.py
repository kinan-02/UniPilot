"""Conservative prerequisite and credit warnings for semester planner views."""

from __future__ import annotations

from typing import Any

from app.planning.prerequisite_resolver import (
    extract_course_numbers_from_text,
    resolve_prerequisite_ids,
)
from app.planning.exam_summary import active_planned_courses
from app.planning.weekly_schedule import build_weekly_schedule_payload, summarize_slot_types
from app.services.graduation_progress_calculator import round_credits


def _completed_course_numbers(completed_records: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for record in completed_records:
        number = record.get("courseNumber")
        if number:
            numbers.add(str(number))
    return numbers


def _completed_course_ids(completed_records: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for record in completed_records:
        course_id = record.get("courseId")
        if course_id is not None:
            ids.add(str(course_id))
    return ids


def assess_prerequisite_warning(
    course: dict[str, Any],
    *,
    completed_records: list[dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
    courses_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return conservative prerequisite status — never overclaim validation."""
    course_number = str(course.get("courseNumber") or "")
    explicit_prereqs = course.get("prerequisites")
    prereq_text = course.get("prerequisitesText")
    parsed_numbers = extract_course_numbers_from_text(prereq_text)
    resolved_ids = resolve_prerequisite_ids(
        course,
        courses_by_number=courses_by_number,
    )

    completed_numbers = _completed_course_numbers(completed_records)
    completed_ids = _completed_course_ids(completed_records)

    if explicit_prereqs:
        missing: list[dict[str, str]] = []
        for prereq_id in explicit_prereqs:
            prereq_key = str(prereq_id)
            if prereq_key in completed_ids:
                continue
            doc = courses_by_id.get(prereq_key)
            missing.append(
                {
                    "courseId": prereq_key,
                    "courseNumber": str(doc.get("courseNumber") or "") if doc else "",
                    "courseTitle": str(
                        doc.get("titleHebrew") or doc.get("title") or ""
                    )
                    if doc
                    else "",
                }
            )
        if missing:
            return {
                "courseNumber": course_number,
                "status": "missing",
                "message": "Some prerequisites appear missing from completed courses",
                "missingPrerequisites": missing,
            }
        return {
            "courseNumber": course_number,
            "status": "satisfied",
            "message": "Parsed prerequisites appear satisfied",
        }

    if resolved_ids:
        missing_numbers: list[str] = []
        for prereq_id in resolved_ids:
            doc = courses_by_id.get(str(prereq_id))
            number = str(doc.get("courseNumber") or "") if doc else ""
            if number and number not in completed_numbers:
                missing_numbers.append(number)
        if missing_numbers:
            return {
                "courseNumber": course_number,
                "status": "missing",
                "message": "Some prerequisites parsed from text appear missing",
                "missingPrerequisiteNumbers": missing_numbers,
                "prerequisitesText": prereq_text,
            }
        return {
            "courseNumber": course_number,
            "status": "satisfied",
            "message": "Prerequisites parsed from text appear satisfied",
            "prerequisitesText": prereq_text,
        }

    if prereq_text and prereq_text.strip():
        return {
            "courseNumber": course_number,
            "status": "manual_verification",
            "message": "Prerequisites require manual verification",
            "prerequisitesText": prereq_text.strip(),
        }

    if parsed_numbers:
        missing_from_text = [n for n in parsed_numbers if n not in completed_numbers]
        if missing_from_text:
            return {
                "courseNumber": course_number,
                "status": "possibly_missing",
                "message": "Prerequisite course numbers found in text — verify manually",
                "missingPrerequisiteNumbers": missing_from_text,
                "prerequisitesText": prereq_text,
            }

    return {
        "courseNumber": course_number,
        "status": "none",
        "message": "No prerequisites listed",
    }


def build_planner_insights(
    plan: dict[str, Any],
    *,
    profile: dict[str, Any] | None,
    completed_records: list[dict[str, Any]],
    catalog_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    primary = (plan.get("semesters") or [{}])[0]
    planned = primary.get("plannedCourses") or []
    active_planned = active_planned_courses(planned)
    weekly = primary.get("weeklySchedule") or {}

    total_credits = round_credits(
        sum(float(c.get("credits") or 0) for c in active_planned)
    )
    max_credits = None
    if profile:
        prefs = profile.get("preferences") or {}
        max_credits = prefs.get("maxCreditsPerSemester")

    courses_by_number = {
        str(c.get("courseNumber") or c.get("number")): c
        for c in catalog_courses
        if c.get("courseNumber") or c.get("number")
    }
    courses_by_id = {
        str(course["_id"]): course for course in catalog_courses if course.get("_id") is not None
    }

    course_warnings: list[dict[str, Any]] = []
    for planned_course in active_planned:
        course_id = str(planned_course.get("courseId") or "")
        catalog_course = courses_by_id.get(course_id)
        if not catalog_course:
            course_warnings.append(
                {
                    "courseId": course_id,
                    "courseNumber": planned_course.get("courseNumber"),
                    "status": "unknown_course",
                    "message": "Course metadata unavailable",
                }
            )
            continue
        warning = assess_prerequisite_warning(
            catalog_course,
            completed_records=completed_records,
            courses_by_number=courses_by_number,
            courses_by_id=courses_by_id,
        )
        warning["courseId"] = course_id
        course_warnings.append(warning)

    active_ids = {
        str(course.get("courseId"))
        for course in active_planned
        if course.get("courseId") is not None
    }
    schedule_entries = [
        entry
        for entry in (weekly.get("entries") or [])
        if str(entry.get("courseId") or "") in active_ids
    ]
    custom_events = weekly.get("customEvents") or primary.get("customEvents") or []
    conflicts = weekly.get("conflicts")
    if conflicts is None and (schedule_entries or custom_events):
        conflicts = build_weekly_schedule_payload(
            schedule_entries,
            custom_events=custom_events,
        )["conflicts"]
    elif conflicts is not None:
        active_numbers = {str(course.get("courseNumber") or "") for course in active_planned}
        conflicts = [
            conflict
            for conflict in conflicts
            if all(number in active_numbers for number in (conflict.get("courseNumbers") or []))
        ]

    credits_warning = None
    if max_credits is not None and total_credits > float(max_credits):
        credits_warning = {
            "status": "over_max",
            "message": f"Plan exceeds preferred max credits ({total_credits} > {max_credits})",
            "totalCredits": total_credits,
            "maxCreditsPerSemester": max_credits,
        }

    return {
        "totalCredits": total_credits,
        "maxCreditsPerSemester": max_credits,
        "creditsWarning": credits_warning,
        "courseWarnings": course_warnings,
        "scheduleConflicts": conflicts or [],
        "scheduleStatus": weekly.get("status"),
    }
