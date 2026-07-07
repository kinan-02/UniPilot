"""Small prerequisite-description helpers extracted from `api`'s `planning/semester_planner.py`.

Only these two functions are needed here (`retrieval/catalog_retriever.py`).
The rest of `semester_planner.py` is the full semester-generation engine and
depends on `graduation_progress_calculator`/`graduation_requirement_links`
— the core, actively-evolving academic engine that intentionally stays in
`api` only (see `services/api/app/routes/internal_agent.py`) rather than
being duplicated here.
"""

from __future__ import annotations

from typing import Any


def normalize_course_id(course_id: Any) -> str:
    return str(course_id)


def describe_missing_prerequisites(
    course: dict[str, Any],
    satisfied_course_ids: set[str],
    courses_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing_prerequisite_ids = [
        normalize_course_id(course_id)
        for course_id in (course.get("prerequisites") or [])
        if normalize_course_id(course_id) not in satisfied_course_ids
    ]

    missing_prerequisites = []
    for course_id in missing_prerequisite_ids:
        prerequisite_course = courses_by_id.get(course_id)
        missing_prerequisites.append(
            {
                "courseId": course_id,
                "courseNumber": (prerequisite_course or {}).get("number"),
                "courseTitle": (prerequisite_course or {}).get("title"),
            }
        )

    labels = [
        entry["courseNumber"] or entry["courseId"]
        for entry in missing_prerequisites
        if entry.get("courseNumber") or entry.get("courseId")
    ]
    reason = (
        f"Blocked until prerequisite course(s) are completed or scheduled earlier: {', '.join(labels)}"
        if labels
        else "Blocked by unsatisfied prerequisites"
    )

    return {
        "missingPrerequisiteIds": missing_prerequisite_ids,
        "missingPrerequisites": missing_prerequisites,
        "reason": reason,
    }
