"""Preview course and schedule suggestions for the manual semester planner."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.schedule_optimizer import (
    build_selection_state_from_existing_planned,
    optimize_schedule_for_planned_courses,
    select_progress_aware_courses,
)
from app.planning.semester_codes import pick_best_offering, plan_semester_to_offering_keys
from app.planning.semester_planner import (
    build_candidate_pools,
    normalize_course_id,
)
from app.planning.prerequisite_resolver import build_courses_by_number, canonical_course_number
from app.repositories import catalog_repository
from app.services.graduation_progress_calculator import build_effective_completions, round_credits
from app.services.semester_plan_service import load_planning_context


def _expand_course_numbers_for_lookup(course_numbers: list[str]) -> list[str]:
    """Include canonical aliases so Mongo lookups match catalog courseNumber keys."""
    expanded: set[str] = set()
    for number in course_numbers:
        raw = str(number or "").strip()
        if not raw:
            continue
        expanded.add(raw)
        canonical = canonical_course_number(raw)
        if canonical:
            expanded.add(canonical)
    return sorted(expanded)


def _index_offering_aliases(
    offerings_by_number: dict[str, dict[str, Any]],
    offering: dict[str, Any],
    *aliases: str,
) -> None:
    keys: set[str] = {str(alias).strip() for alias in aliases if str(alias).strip()}
    offering_number = str(offering.get("courseNumber") or "").strip()
    if offering_number:
        keys.add(offering_number)
    canonical = canonical_course_number(offering_number)
    if canonical:
        keys.add(canonical)
    for key in keys:
        offerings_by_number[key] = offering


async def _load_exact_term_offerings(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
    *,
    academic_year: int,
    semester_code: int,
) -> dict[str, dict[str, Any]]:
    """Return offerings only for the exact requested academic year and term."""
    lookup_numbers = _expand_course_numbers_for_lookup(course_numbers)
    if not lookup_numbers:
        return {}

    grouped = await catalog_repository.list_offerings_grouped_for_courses(
        database,
        lookup_numbers,
        academic_year=academic_year,
        semester_code=semester_code,
    )
    offerings_by_number: dict[str, dict[str, Any]] = {}
    for number in lookup_numbers:
        offering = pick_best_offering(
            grouped.get(number, []),
            preferred_academic_year=academic_year,
            semester_code=semester_code,
        )
        if (
            offering is not None
            and int(offering.get("academicYear") or 0) == academic_year
            and int(offering.get("semesterCode") or 0) == semester_code
        ):
            _index_offering_aliases(offerings_by_number, offering, number)

    for number in lookup_numbers:
        canonical = canonical_course_number(number)
        if canonical and canonical in offerings_by_number:
            offerings_by_number[number] = offerings_by_number[canonical]

    return offerings_by_number


def _draft_course_ids(existing_planned_courses: list[dict[str, Any]] | None) -> set[str]:
    draft_ids: set[str] = set()
    for course in existing_planned_courses or []:
        if course.get("isActive", True) is False:
            continue
        course_id = normalize_course_id(str(course.get("courseId") or ""))
        if course_id:
            draft_ids.add(course_id)
    return draft_ids


async def suggest_semester_courses(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    semester_code: str,
    max_credits: float | None = None,
    existing_planned_courses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    offering_keys = plan_semester_to_offering_keys(semester_code)
    if offering_keys is None:
        return {"status": "validation_error", "errors": ["Invalid semesterCode"]}

    academic_year, term_semester_code = offering_keys
    profile = context["profile"]
    degree = context["degree"]
    preferences = profile.get("preferences") or {}
    max_credits_limit = round_credits(
        max_credits
        if max_credits is not None
        else preferences.get("maxCreditsPerSemester", 18.0)
    )

    effective_completions = build_effective_completions(context["completedCourseRecords"])
    completed_course_ids = set(effective_completions.keys())

    pools = build_candidate_pools(
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        program_code=str(degree.get("programCode") or degree.get("code") or ""),
        completed_course_ids=completed_course_ids,
    )

    candidate_numbers = [
        str(course.get("number") or "")
        for course in [*pools["mandatoryCandidates"], *pools["electiveCandidates"]]
        if course.get("number")
    ]
    existing_numbers = [
        str(course.get("courseNumber") or "")
        for course in existing_planned_courses or []
        if course.get("courseNumber")
    ]
    offerings_by_number = await _load_exact_term_offerings(
        database,
        sorted(set([*candidate_numbers, *existing_numbers])),
        academic_year=academic_year,
        semester_code=term_semester_code,
    )

    initial_state = None
    reserved_credits = 0.0
    if existing_planned_courses:
        initial_state = build_selection_state_from_existing_planned(
            satisfied_course_ids=completed_course_ids,
            existing_planned=existing_planned_courses,
            offerings_by_number=offerings_by_number,
        )
        reserved_credits = float(initial_state["totalCredits"])

    draft_course_ids = _draft_course_ids(existing_planned_courses)
    matrix_progress_ids = completed_course_ids | draft_course_ids

    selection = select_progress_aware_courses(
        mandatory_candidates=pools["mandatoryCandidates"],
        elective_candidates=pools["electiveCandidates"],
        satisfied_course_ids=completed_course_ids,
        max_credits_limit=max_credits_limit,
        offerings_by_number=offerings_by_number,
        semester_matrix_documents=context["semesterMatrixDocuments"],
        courses_by_id=pools["coursesById"],
        courses_by_number=build_courses_by_number(context["catalogCourses"]),
        academic_year=academic_year,
        semester_code=term_semester_code,
        initial_state=initial_state,
        matrix_progress_course_ids=matrix_progress_ids,
    )

    selected_courses = selection["selectedCourses"]
    semester_total_credits = float(selection["totalCredits"])
    new_credits = round_credits(max(0.0, semester_total_credits - reserved_credits))
    partial_plan = semester_total_credits < max_credits_limit and (
        len(selected_courses) > 0 or reserved_credits > 0
    )

    explanation = {
        "semesterCode": semester_code,
        "maxCredits": max_credits_limit,
        "totalRecommendedCredits": new_credits,
        "semesterTotalCredits": semester_total_credits,
        "reservedCredits": reserved_credits,
        "selectedCount": len(selected_courses),
        "partialPlan": partial_plan,
        "emptyPlan": len(selected_courses) == 0 and reserved_credits == 0,
        "skippedDueToWorkload": selection["skippedDueToWorkload"],
        "skippedDueToConflicts": selection.get("skippedDueToConflicts") or [],
        "skippedDueToUnavailable": selection.get("skippedDueToUnavailable") or [],
        "activeMatrixSemester": selection.get("activeMatrixSemester"),
        "rulesApplied": [
            "Prioritize earliest incomplete matrix-semester courses, then later matrix semesters for returning students",
            "Include remaining hard-requirement mandatory courses from graduation progress",
            "Only include courses offered in the selected semester with a published schedule",
            "Respect graduation progress and prerequisite eligibility",
            "Respect maxCredits workload limit",
            "Skip courses with exam-date or lesson-schedule conflicts",
            "Add electives only after mandatory priorities are exhausted",
        ],
    }

    return {
        "status": "ok",
        "plannedCourses": selected_courses,
        "explanation": explanation,
    }


async def suggest_semester_schedule(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    semester_code: str,
    planned_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    offering_keys = plan_semester_to_offering_keys(semester_code)
    if offering_keys is None:
        return {"status": "validation_error", "errors": ["Invalid semesterCode"]}

    academic_year, term_semester_code = offering_keys
    active_courses = [course for course in planned_courses if course.get("isActive", True) is not False]
    if not active_courses:
        return {"status": "validation_error", "errors": ["At least one active planned course is required"]}

    course_numbers = [
        str(course.get("courseNumber") or "")
        for course in active_courses
        if course.get("courseNumber")
    ]
    offerings_by_number = await _load_exact_term_offerings(
        database,
        course_numbers,
        academic_year=academic_year,
        semester_code=term_semester_code,
    )

    optimized = optimize_schedule_for_planned_courses(
        active_courses,
        offerings_by_number=offerings_by_number,
        academic_year=academic_year,
        semester_code=term_semester_code,
    )

    return {
        "status": "ok",
        "selections": optimized["selections"],
        "skippedCourses": optimized["skippedCourses"],
        "examSummary": optimized["examSummary"],
    }
