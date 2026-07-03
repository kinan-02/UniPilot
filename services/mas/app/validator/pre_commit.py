"""Deterministic pre-commit validation for MAS decisions."""

from __future__ import annotations

from typing import Any

from app.orchestrator.artifacts import Violation
from app.orchestrator.violations import violations_from_messages
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.api_catalog import (
    api_offered_course_numbers,
    course_is_api_validated,
    is_course_in_active_catalog,
    uses_api_semester_catalog,
)
from app.services.schedule_conflict import detect_plan_schedule_conflicts


def validate_plan_proposal(
    *,
    course_ids: list[str],
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any] | None = None,
) -> tuple[bool, list[str], list[str]]:
    """
    Validate a proposed plan against wiki + semester JSON ground truth.

    When API Mongo catalog is present on user_context, catalog membership is
    checked against term offerings from the Progress-aligned planner instead of
    the local semester JSON file.

    Returns (ok, violations, references).
    """
    violations: list[str] = []
    references: list[str] = []

    if not course_ids:
        violations.append("Plan must include at least one course.")
        return False, violations, references

    api_catalog = uses_api_semester_catalog(user_context)
    if api_catalog:
        references.append("catalog:source=api_mongo")

    for course_id in course_ids:
        if not is_course_in_active_catalog(
            engine=engine,
            course_id=course_id,
            user_context=user_context,
        ):
            if api_catalog:
                violations.append(
                    f"Course {course_id} is not offered in the selected semester catalog."
                )
            else:
                violations.append(f"Course {course_id} is not in the active semester catalog.")
            continue

        if api_catalog and course_is_api_validated(course_id, user_context):
            references.append(f"eligibility:{course_id}:eligible=true:api_validated")
            continue

        eligible, missing = engine.evaluate_eligibility(course_id, completed_courses)
        references.append(f"eligibility:{course_id}:eligible={eligible}")
        if not eligible:
            violations.append(
                f"Course {course_id} has unmet prerequisites: {', '.join(missing) or 'unknown'}"
            )

    if len(course_ids) > 1:
        conflicts, conflict_refs = detect_plan_schedule_conflicts(engine, course_ids)
        references.extend(conflict_refs)
        for conflict in conflicts:
            violations.append(
                "Schedule conflict between "
                f"{conflict['courseA']} and {conflict['courseB']} on "
                f"{conflict['day']} ({conflict['timeRangeA']} vs {conflict['timeRangeB']})."
            )

    if api_catalog:
        offered = api_offered_course_numbers(user_context) or set()
        references.append(f"catalog:offered_count={len(offered)}")

    return len(violations) == 0, violations, references


def validate_plan_proposal_typed(
    *,
    course_ids: list[str],
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    user_context: dict[str, Any] | None = None,
) -> tuple[bool, list[Violation], list[str]]:
    """Typed wrapper around validate_plan_proposal."""
    ok, messages, references = validate_plan_proposal(
        course_ids=course_ids,
        engine=engine,
        completed_courses=completed_courses,
        user_context=user_context,
    )
    return ok, violations_from_messages(messages), references
