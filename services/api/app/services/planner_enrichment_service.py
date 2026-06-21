"""Attach planner insights (credits, conflicts, prerequisites, exams) to semester plan responses."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.exam_summary import active_planned_courses, build_exam_summary
from app.planning.planner_warnings import build_planner_insights
from app.planning.semester_codes import plan_semester_to_offering_keys
from app.repositories import catalog_repository
from app.repositories.catalog_repository import find_courses_by_ids
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.manual_semester_plan_service import is_course_active


async def _offerings_for_planned_courses(
    database: AsyncIOMotorDatabase,
    *,
    planned_courses: list[dict[str, Any]],
    semester_code: str,
) -> dict[str, dict[str, Any]]:
    offering_keys = plan_semester_to_offering_keys(semester_code)
    if not offering_keys:
        return {}

    academic_year, technion_code = offering_keys
    offerings_by_number: dict[str, dict[str, Any]] = {}
    for planned in planned_courses:
        course_number = str(planned.get("courseNumber") or "")
        if not course_number or course_number in offerings_by_number:
            continue
        offerings = await catalog_repository.list_offerings_for_course(
            database,
            course_number,
            semester_code=technion_code,
        )
        from app.planning.semester_codes import pick_best_offering

        best = pick_best_offering(
            offerings,
            preferred_academic_year=academic_year,
            semester_code=technion_code,
        )
        if best:
            offerings_by_number[course_number] = best
    return offerings_by_number


def _stale_course_warnings(
    planned_courses: list[dict[str, Any]],
    offerings_by_number: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for planned in planned_courses:
        course_number = str(planned.get("courseNumber") or "")
        if not course_number:
            continue
        offering = offerings_by_number.get(course_number)
        if offering is None:
            warnings.append(
                {
                    "courseNumber": course_number,
                    "courseId": planned.get("courseId"),
                    "status": "offering_missing",
                    "message": (
                        "This course is no longer available in the selected semester data"
                    ),
                }
            )
    return warnings


async def enrich_semester_plan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Return plan dict with plannerInsights — does not mutate stored plan."""
    primary = (plan.get("semesters") or [{}])[0]
    planned = primary.get("plannedCourses") or []
    active = active_planned_courses(planned)
    course_ids = [
        str(course.get("courseId"))
        for course in planned
        if course.get("courseId") is not None
    ]

    profile = await find_student_profile_by_user_id(database, user_id)
    completed_records = await find_all_completed_courses_by_user_id(database, user_id)
    catalog_courses = await find_courses_by_ids(database, course_ids)
    offerings_by_number = await _offerings_for_planned_courses(
        database,
        planned_courses=planned,
        semester_code=str(primary.get("semesterCode") or ""),
    )

    insights = build_planner_insights(
        plan,
        profile=profile,
        completed_records=completed_records,
        catalog_courses=catalog_courses,
    )
    insights["activeCourseCount"] = len(active)
    insights["totalCourseCount"] = len(planned)
    insights["examSummary"] = build_exam_summary(
        planned,
        offerings_by_number,
        include_inactive=False,
    )
    insights["staleCourseWarnings"] = _stale_course_warnings(planned, offerings_by_number)

    enriched = dict(plan)
    enriched["plannerInsights"] = insights
    return enriched
