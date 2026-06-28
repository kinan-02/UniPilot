"""Graduation progress orchestration (Phase 15)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.graduation_progress_calculator import calculate_graduation_progress
from app.services.graduation_catalog_context import enrich_pool_documents_for_program

ProgressStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
]


async def get_graduation_progress_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found"}

    degree_id = profile.get("degreeId")
    if not degree_id:
        return {"status": "degree_not_selected"}

    degree_program = await catalog_repository.find_degree_program_by_id(
        database,
        str(degree_id),
    )
    if not degree_program:
        return {"status": "degree_not_found"}

    program_code = str(degree_program["programCode"])

    import asyncio

    hard_requirements_task = catalog_repository.list_hard_requirements_for_program(
        database,
        program_code,
        include_internal=True,
    )
    pools_task = catalog_repository.list_course_pools_for_program(database, program_code)
    matrix_task = catalog_repository.list_semester_matrix_rules_for_program(
        database,
        program_code,
    )
    completed_task = find_all_completed_courses_by_user_id(database, user_id)

    hard_requirements, pool_documents, semester_matrix_documents, completed_records = await asyncio.gather(
        hard_requirements_task,
        pools_task,
        matrix_task,
        completed_task,
    )

    pool_documents = await enrich_pool_documents_for_program(
        database,
        program_code=program_code,
        pool_documents=pool_documents,
    )

    course_ids = [str(record["courseId"]) for record in completed_records]
    catalog_courses = await catalog_repository.find_courses_by_ids(database, course_ids)
    catalog_courses_by_id = {str(course["_id"]): course for course in catalog_courses}

    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
        semester_matrix_documents=semester_matrix_documents,
    )

    return {"status": "ok", "progress": progress}
