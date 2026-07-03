"""Academic risk analysis orchestration (Phase 17)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.academic_risk_analyzer import (
    analyze_academic_risks,
    course_number,
    course_title,
    normalize_course_id,
)
from app.repositories import catalog_repository
from app.repositories.academic_risk_repository import create_academic_risk_analysis
from app.repositories.semester_plan_repository import find_semester_plan_by_id_and_user_id
from app.services.graduation_progress_calculator import round_credits
from app.services.semester_plan_service import load_planning_context


def build_plan_view_from_semester_plan(plan_document: dict[str, Any]) -> dict[str, Any]:
    semesters = plan_document.get("semesters") or []
    primary_semester = semesters[0] if semesters else None
    constraints = (primary_semester or {}).get("constraintsSnapshot") or {}

    return {
        "planId": str(plan_document["_id"]),
        "semesterCode": (primary_semester or {}).get("semesterCode"),
        "plannedCourses": (primary_semester or {}).get("plannedCourses") or [],
        "maxCredits": constraints.get("maxCredits") or (primary_semester or {}).get("goalCredits"),
        "minCredits": constraints.get("minCredits") or 0,
        "explanation": plan_document.get("explanation") or {},
        "plannerType": plan_document.get("plannerType"),
        "analysisSource": "semester_plan",
    }


async def build_plan_view_from_adhoc(
    database: AsyncIOMotorDatabase,
    degree: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    planned_courses: list[dict[str, Any]] = []

    for course_id in options["courseIds"]:
        catalog_course = await catalog_repository.find_course_by_id(database, course_id)
        if not catalog_course:
            planned_courses.append(
                {
                    "courseId": normalize_course_id(course_id),
                    "courseNumber": None,
                    "courseTitle": None,
                    "credits": 0,
                    "category": "adhoc",
                    "catalogScopeValid": True,
                    "reason": "Ad-hoc proposed course",
                }
            )
            continue

        number = course_number(catalog_course)
        title = course_title(catalog_course)
        in_scope = (
            catalog_course.get("institutionId") == degree.get("institutionId")
            and catalog_course.get("catalogYear") == degree.get("catalogYear")
        )

        if not in_scope:
            planned_courses.append(
                {
                    "courseId": normalize_course_id(course_id),
                    "courseNumber": number,
                    "courseTitle": title,
                    "credits": round_credits(catalog_course.get("credits") or 0),
                    "category": "adhoc",
                    "catalogScopeValid": False,
                    "reason": "Ad-hoc proposed course outside active degree catalog scope",
                }
            )
            continue

        planned_courses.append(
            {
                "courseId": normalize_course_id(catalog_course["_id"]),
                "courseNumber": number,
                "courseTitle": title,
                "credits": round_credits(catalog_course.get("credits") or 0),
                "category": "adhoc",
                "catalogScopeValid": True,
                "reason": "Ad-hoc proposed course",
            }
        )

    return {
        "planId": None,
        "semesterCode": options["semesterCode"],
        "plannedCourses": planned_courses,
        "maxCredits": options.get("maxCredits"),
        "minCredits": options.get("minCredits") or 0,
        "explanation": {},
        "plannerType": None,
        "analysisSource": "adhoc_courses",
    }


async def preview_academic_risks_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    course_numbers: list[str],
    semester_code: str,
    max_credits: float | None = None,
    min_credits: float | None = None,
) -> dict[str, Any]:
    """Analyze ad-hoc course numbers without persisting (MAS Risk Sentinel integration)."""
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    catalog_courses = await catalog_repository.find_courses_by_numbers(database, course_numbers)
    courses_by_number: dict[str, dict[str, Any]] = {}
    for course in catalog_courses:
        number = str(course.get("courseNumber") or course.get("number") or "")
        if not number:
            continue
        courses_by_number[number] = course
        if number.isdigit():
            courses_by_number[number.zfill(8)] = course

    resolved_ids: list[str] = []
    for number in course_numbers:
        normalized = number.zfill(8) if number.isdigit() else number
        course = courses_by_number.get(normalized) or courses_by_number.get(number)
        if course is not None:
            resolved_ids.append(str(course["_id"]))

    if not resolved_ids:
        return {"status": "validation_error", "errors": ["No matching catalog courses for analysis."]}

    options = {
        "semesterCode": semester_code,
        "courseIds": resolved_ids,
        "maxCredits": max_credits,
        "minCredits": min_credits,
    }
    plan_view = await build_plan_view_from_adhoc(database, context["degree"], options)
    analysis_data = analyze_academic_risks(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        pool_documents=context["poolDocuments"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        plan_view=plan_view,
    )
    return {"status": "ok", "analysis": analysis_data}


async def analyze_and_store_academic_risks(
    database: AsyncIOMotorDatabase,
    user_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    if options.get("planId"):
        plan = await find_semester_plan_by_id_and_user_id(
            database,
            options["planId"],
            user_id,
        )
        if not plan:
            return {"status": "plan_not_found"}
        plan_view = build_plan_view_from_semester_plan(plan)
    else:
        plan_view = await build_plan_view_from_adhoc(database, context["degree"], options)

    analysis_data = analyze_academic_risks(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        pool_documents=context["poolDocuments"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        plan_view=plan_view,
    )

    stored_analysis = await create_academic_risk_analysis(database, user_id, analysis_data)
    return {"status": "ok", "analysis": stored_analysis}


async def list_academic_risk_analyses_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    pagination: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.academic_risk_repository import (
        find_academic_risk_analyses_by_user_id,
    )

    return await find_academic_risk_analyses_by_user_id(
        database,
        user_id,
        page=pagination.get("page") or 1,
        limit=pagination.get("limit") or 50,
    )


async def get_academic_risk_analysis_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    analysis_id: str,
) -> dict[str, Any]:
    from app.repositories.academic_risk_repository import (
        find_academic_risk_analysis_by_id_and_user_id,
    )

    analysis = await find_academic_risk_analysis_by_id_and_user_id(
        database,
        analysis_id,
        user_id,
    )
    if not analysis:
        return {"status": "not_found"}

    return {"status": "ok", "analysis": analysis}
