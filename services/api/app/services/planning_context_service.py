"""Progress-page-aligned planning context for MAS session bootstrap."""

from __future__ import annotations

from typing import Any

from app.planning.prerequisite_resolver import canonical_course_number
from app.services.course_reference_keys import course_number_keys

SATISFIED_BUCKET_STATUSES = frozenset({"satisfied", "complete", "mandatory_requirements_met"})


def _append_course_number(numbers: set[str], raw: Any) -> None:
    if raw is None:
        return
    for key in course_number_keys(str(raw)):
        if key:
            numbers.add(key)


def build_full_transcript_course_numbers(graduation_progress: dict[str, Any]) -> list[str]:
    """
    Mirror Progress page ``buildFullTranscriptCourseNumbers``.

    Includes bucket completions, completed mandatory rows, and ineligible credits.
    """
    numbers: set[str] = set()

    for bucket in graduation_progress.get("requirementProgress") or []:
        if not isinstance(bucket, dict):
            continue
        for course in bucket.get("completedCourses") or []:
            if isinstance(course, dict):
                _append_course_number(numbers, course.get("courseNumber") or course.get("number"))

    for course in graduation_progress.get("completedMandatoryCourses") or []:
        if isinstance(course, dict):
            _append_course_number(numbers, course.get("courseNumber") or course.get("number"))

    for entry in graduation_progress.get("ineligibleCredits") or []:
        if isinstance(entry, dict):
            _append_course_number(numbers, entry.get("courseNumber") or entry.get("number"))

    return sorted(numbers)


def build_path_priority_course_numbers(
    graduation_progress: dict[str, Any],
    *,
    curriculum_graph: dict[str, Any] | None = None,
) -> list[str]:
    """
    Ordered remaining degree-path courses aligned with Progress prioritization.

    Mandatory remaining first, then unsatisfied requirement bucket remainders.
    """
    _ = curriculum_graph  # reserved for equivalence expansion in a follow-up
    ordered: list[str] = []
    seen: set[str] = set()

    def append(raw: Any) -> None:
        canonical = canonical_course_number(str(raw or ""))
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        ordered.append(canonical)

    for entry in graduation_progress.get("remainingMandatoryCourses") or []:
        if isinstance(entry, dict):
            append(entry.get("courseNumber") or entry.get("number"))

    for bucket in graduation_progress.get("requirementProgress") or []:
        if not isinstance(bucket, dict):
            continue
        status = str(bucket.get("status") or "")
        if status in SATISFIED_BUCKET_STATUSES:
            continue
        min_credits = float(bucket.get("minCredits") or 0)
        credits_completed = float(bucket.get("creditsCompleted") or 0)
        if bucket.get("isMandatory") is False and min_credits > 0 and credits_completed >= min_credits:
            continue
        for entry in bucket.get("remainingCourses") or []:
            if isinstance(entry, dict):
                append(entry.get("courseNumber") or entry.get("number"))

    return ordered


def build_planning_context(
    *,
    graduation_progress: dict[str, Any] | None,
    curriculum_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serializable planning snapshot consumed by MAS (Progress-page equivalent)."""
    if not isinstance(graduation_progress, dict):
        return {
            "status": "graduation_unavailable",
            "transcriptCourseNumbers": [],
            "pathPriorityCourseNumbers": [],
            "creditsRemaining": None,
            "remainingMandatoryCount": 0,
            "requirementBucketCount": 0,
        }

    transcript = build_full_transcript_course_numbers(graduation_progress)
    priorities = build_path_priority_course_numbers(
        graduation_progress,
        curriculum_graph=curriculum_graph,
    )
    requirement_progress = graduation_progress.get("requirementProgress") or []

    return {
        "status": "ok",
        "transcriptCourseNumbers": transcript,
        "pathPriorityCourseNumbers": priorities,
        "creditsRemaining": graduation_progress.get("creditsRemaining"),
        "remainingMandatoryCount": len(graduation_progress.get("remainingMandatoryCourses") or []),
        "requirementBucketCount": len(requirement_progress) if isinstance(requirement_progress, list) else 0,
        "completionPercentage": graduation_progress.get("completionPercentage"),
    }
