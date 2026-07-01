"""Graduation progress orchestration (Phase 15)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.track_registry import (
    program_code_for_track_slug,
    resolve_track_slug_from_program,
)
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.course_reference_keys import course_number_keys
from app.services.graduation_progress_calculator import calculate_graduation_progress
from app.services.graduation_catalog_context import enrich_pool_documents_for_program

ProgressStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
]


MAX_OVERLAP_CATALOG_HOPS = 10


async def _load_transitive_overlap_partner_catalog(
    database: AsyncIOMotorDatabase,
    catalog_courses_by_id: dict[str, dict[str, Any]],
) -> None:
    """Fetch catalog rows for overlap partners until the group closure is loaded."""
    from app.services.catalog_overlap_groups import collect_overlap_partner_numbers
    from app.services.course_reference_keys import course_number_keys

    known_numbers: set[str] = set()
    for course in catalog_courses_by_id.values():
        number = course.get("courseNumber") or course.get("number")
        if number is not None:
            known_numbers |= course_number_keys(str(number))

    for _ in range(MAX_OVERLAP_CATALOG_HOPS):
        partner_numbers = collect_overlap_partner_numbers(list(catalog_courses_by_id.values()))
        missing_partners = sorted(number for number in partner_numbers if number not in known_numbers)
        if not missing_partners:
            return

        partner_courses = await catalog_repository.find_courses_by_numbers(
            database,
            missing_partners,
        )
        if not partner_courses:
            return

        previous_size = len(known_numbers)
        for course in partner_courses:
            catalog_courses_by_id[str(course["_id"])] = course
            number = course.get("courseNumber") or course.get("number")
            if number is not None:
                known_numbers |= course_number_keys(str(number))

        if len(known_numbers) == previous_size:
            return


async def _synthetic_completed_records_for_numbers(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
) -> list[dict[str, Any]]:
    """Build in-memory completed-course rows for hypothetical preview (not persisted)."""
    if not course_numbers:
        return []

    catalog_courses = await catalog_repository.find_courses_by_numbers(database, course_numbers)
    by_number: dict[str, dict[str, Any]] = {}
    for course in catalog_courses:
        number = course.get("courseNumber") or course.get("number")
        if number is None:
            continue
        for key in course_number_keys(str(number)):
            by_number[key] = course

    records: list[dict[str, Any]] = []
    for raw_number in course_numbers:
        course = None
        for key in course_number_keys(raw_number):
            course = by_number.get(key)
            if course is not None:
                break
        if course is None:
            continue
        records.append(
            {
                "courseId": course["_id"],
                "semesterCode": "MAS_PREVIEW",
                "grade": 82,
                "gradePoints": 3.0,
                "creditsEarned": float(course.get("credits") or 0),
                "attempt": 1,
                "source": "mas_preview",
            }
        )
    return records


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

    academic_path = profile.get("academicPath") or {}
    track_slug = academic_path.get("trackSlug") or resolve_track_slug_from_program(degree_program)
    program_code = str(
        degree_program.get("programCode") or program_code_for_track_slug(track_slug) or ""
    )
    if not program_code:
        return {"status": "degree_not_found"}

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

    await _load_transitive_overlap_partner_catalog(database, catalog_courses_by_id)

    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
        semester_matrix_documents=semester_matrix_documents,
    )

    return {"status": "ok", "progress": progress}


async def preview_graduation_progress_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    completed_course_numbers: list[str] | None = None,
    additional_course_numbers: list[str] | None = None,
) -> dict[str, Any]:
    """
    Recompute graduation progress for a hypothetical completed-course set.

    When ``completed_course_numbers`` is provided, it replaces the student's stored
    completions (MAS what-if baseline). ``additional_course_numbers`` are merged
    on top for per-variant plan projection.
    """
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

    academic_path = profile.get("academicPath") or {}
    track_slug = academic_path.get("trackSlug") or resolve_track_slug_from_program(degree_program)
    program_code = str(
        degree_program.get("programCode") or program_code_for_track_slug(track_slug) or ""
    )
    if not program_code:
        return {"status": "degree_not_found"}

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

    hard_requirements, pool_documents, semester_matrix_documents = await asyncio.gather(
        hard_requirements_task,
        pools_task,
        matrix_task,
    )

    pool_documents = await enrich_pool_documents_for_program(
        database,
        program_code=program_code,
        pool_documents=pool_documents,
    )

    if completed_course_numbers is not None:
        completed_records = await _synthetic_completed_records_for_numbers(
            database,
            list(dict.fromkeys(completed_course_numbers)),
        )
    else:
        completed_records = await find_all_completed_courses_by_user_id(database, user_id)

    if additional_course_numbers:
        existing_numbers: set[str] = set()
        if completed_records:
            course_ids = [str(record["courseId"]) for record in completed_records if record.get("courseId")]
            catalog_courses = await catalog_repository.find_courses_by_ids(database, course_ids)
            for course in catalog_courses:
                number = course.get("courseNumber") or course.get("number")
                if number is not None:
                    existing_numbers |= course_number_keys(str(number))

        to_add = [
            number
            for number in dict.fromkeys(additional_course_numbers)
            if not any(key in existing_numbers for key in course_number_keys(number))
        ]
        if to_add:
            completed_records = [
                *completed_records,
                *await _synthetic_completed_records_for_numbers(database, to_add),
            ]

    course_ids = [str(record["courseId"]) for record in completed_records]
    catalog_courses = await catalog_repository.find_courses_by_ids(database, course_ids)
    catalog_courses_by_id = {str(course["_id"]): course for course in catalog_courses}

    await _load_transitive_overlap_partner_catalog(database, catalog_courses_by_id)

    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
        semester_matrix_documents=semester_matrix_documents,
    )
    progress["previewMeta"] = {
        "source": "api_recompute",
        "completedCourseCount": len(completed_records),
        "additionalCourseNumbers": list(additional_course_numbers or []),
        "usedCompletedOverride": completed_course_numbers is not None,
    }

    return {"status": "ok", "progress": progress}
