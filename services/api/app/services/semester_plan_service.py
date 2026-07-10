"""Semester plan orchestration (Phase 16)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.semester_planner import generate_deterministic_semester_plan
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.semester_plan_repository import create_semester_plan
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.graduation_progress_calculator import calculate_graduation_progress

PlanningStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
]


def _pool_course_numbers(pool_document: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for reference in pool_document.get("courseReferences") or []:
        number = reference.get("courseNumber")
        if number is not None:
            numbers.add(str(number))
    return numbers


def _pool_allowed_prefixes(pool_document: dict[str, Any]) -> list[str]:
    rule = pool_document.get("ruleExpression") or {}
    return [str(prefix) for prefix in (rule.get("allowedPrefixes") or [])]


def _matrix_course_numbers(matrix_documents: list[dict[str, Any]]) -> set[str]:
    numbers: set[str] = set()
    for document in matrix_documents:
        for reference in document.get("courseReferences") or []:
            number = reference.get("courseNumber")
            if number is not None:
                numbers.add(str(number))
    return numbers


def _collect_planning_course_numbers(
    *,
    graduation_progress: dict[str, Any],
    hard_requirements: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    semester_matrix_documents: list[dict[str, Any]],
) -> set[str]:
    numbers: set[str] = set()

    for course_ref in graduation_progress.get("remainingMandatoryCourses") or []:
        number = course_ref.get("courseNumber")
        if number is not None:
            numbers.add(str(number))

    for entry in graduation_progress.get("requirementProgress") or []:
        for course_ref in entry.get("remainingCourses") or []:
            number = course_ref.get("courseNumber")
            if number is not None:
                numbers.add(str(number))

    for requirement in hard_requirements:
        for reference in requirement.get("courseReferences") or []:
            number = reference.get("courseNumber")
            if number is not None:
                numbers.add(str(number))

    for pool_document in pool_documents:
        numbers.update(_pool_course_numbers(pool_document))

    numbers.update(_matrix_course_numbers(semester_matrix_documents))

    return numbers


async def _load_planning_catalog_courses(
    database: AsyncIOMotorDatabase,
    *,
    graduation_progress: dict[str, Any],
    hard_requirements: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    semester_matrix_documents: list[dict[str, Any]],
    completed_course_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    course_ids = {str(record["courseId"]) for record in completed_course_records}
    for course_ref in graduation_progress.get("remainingMandatoryCourses") or []:
        if course_ref.get("courseId"):
            course_ids.add(str(course_ref["courseId"]))

    by_id = await catalog_repository.find_courses_by_ids(database, list(course_ids))

    numbers = _collect_planning_course_numbers(
        graduation_progress=graduation_progress,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        semester_matrix_documents=semester_matrix_documents,
    )
    by_number: list[dict[str, Any]] = []
    if numbers:
        by_number = await catalog_repository.find_courses_by_numbers(database, sorted(numbers))

    prefixes: set[str] = set()
    for pool_document in pool_documents:
        prefixes.update(_pool_allowed_prefixes(pool_document))
    prefix_courses = await catalog_repository.list_courses_by_number_prefixes(
        database,
        sorted(prefixes),
    )

    merged: dict[str, dict[str, Any]] = {}
    for course in [*by_id, *by_number, *prefix_courses]:
        merged[str(course["_id"])] = course
    return list(merged.values())


async def load_planning_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found"}

    degree_id = profile.get("degreeId")
    if not degree_id:
        return {"status": "degree_not_selected"}

    degree_program = await catalog_repository.find_degree_program_by_id(database, str(degree_id))
    if not degree_program:
        return {"status": "degree_not_found"}

    program_code = str(degree_program["programCode"])

    hard_requirements_task = catalog_repository.list_hard_requirements_for_program(
        database,
        program_code,
        include_internal=True,
    )
    pools_task = catalog_repository.list_course_pools_for_program(database, program_code)
    matrix_task = catalog_repository.list_semester_matrix_rules_for_program(database, program_code)
    completed_task = find_all_completed_courses_by_user_id(database, user_id)

    hard_requirements, pool_documents, semester_matrix_documents, completed_course_records = await asyncio.gather(
        hard_requirements_task,
        pools_task,
        matrix_task,
        completed_task,
    )

    completed_ids = [str(record["courseId"]) for record in completed_course_records]
    completed_catalog = await catalog_repository.find_courses_by_ids(database, completed_ids)
    catalog_courses_by_id = {str(course["_id"]): course for course in completed_catalog}

    graduation_progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_course_records,
    )

    catalog_courses = await _load_planning_catalog_courses(
        database,
        graduation_progress=graduation_progress,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        semester_matrix_documents=semester_matrix_documents,
        completed_course_records=completed_course_records,
    )

    return {
        "status": "ok",
        "profile": profile,
        "degree": degree_program,
        "hardRequirements": hard_requirements,
        "poolDocuments": pool_documents,
        "semesterMatrixDocuments": semester_matrix_documents,
        "catalogCourses": catalog_courses,
        "completedCourseRecords": completed_course_records,
        "graduationProgress": graduation_progress,
    }


async def generate_and_store_semester_plan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    plan_data = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        semester_code=options["semesterCode"],
        max_credits=options.get("maxCredits"),
        min_credits=options.get("minCredits"),
        name=options.get("name"),
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
    )

    stored_plan = await create_semester_plan(database, user_id, plan_data)
    from app.services.watchdog_enqueue import maybe_enqueue_watchdog_scan

    await maybe_enqueue_watchdog_scan(
        database,
        user_id,
        "new_plan",
        plan_id=str(stored_plan["_id"]),
    )
    return {"status": "ok", "plan": stored_plan}
