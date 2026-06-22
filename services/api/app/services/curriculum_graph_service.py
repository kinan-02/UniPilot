"""Curriculum graph orchestration with Redis cache (track + catalog version)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.graph_builder import build_base_curriculum_graph
from app.curriculum.graph_overlay import enrich_completed_records, overlay_transcript_on_graph
from app.curriculum.track_registry import (
    program_code_for_track_slug,
    resolve_track_slug_from_program,
)
from app.planning.academic_risk_analyzer import normalize_course_id
from app.repositories import catalog_repository
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.catalog_cache import get_cached_json, set_cached_json


def curriculum_graph_cache_key(
    *,
    program_code: str,
    catalog_version: str,
) -> str:
    return f"curriculum-graph:base:v3:{program_code}:{catalog_version}"


def _matrix_course_numbers(semester_matrix_documents: list[dict[str, Any]]) -> list[str]:
    numbers: list[str] = []
    seen: set[str] = set()
    for document in semester_matrix_documents:
        for reference in document.get("courseReferences") or []:
            number = reference.get("courseNumber")
            if number and number not in seen:
                seen.add(number)
                numbers.append(number)
    return numbers


async def _load_base_graph(
    database: AsyncIOMotorDatabase,
    *,
    track_slug: str,
    program_code: str,
    catalog_year: int,
    catalog_version: str,
) -> dict[str, Any] | None:
    cache_key = curriculum_graph_cache_key(
        program_code=program_code,
        catalog_version=catalog_version,
    )
    cached = await get_cached_json(cache_key)
    if cached is not None:
        return cached

    semester_matrix_documents = await catalog_repository.list_semester_matrix_rules_for_program(
        database,
        program_code,
    )
    pool_documents = await catalog_repository.list_course_pools_for_program(
        database,
        program_code,
    )

    if not semester_matrix_documents:
        return None

    course_numbers = _matrix_course_numbers(semester_matrix_documents)
    catalog_courses = await catalog_repository.find_courses_by_numbers(
        database,
        course_numbers,
    )

    base_graph = build_base_curriculum_graph(
        track_slug=track_slug,
        program_code=program_code,
        catalog_year=catalog_year,
        catalog_version=catalog_version,
        semester_matrix_documents=semester_matrix_documents,
        pool_documents=pool_documents,
        catalog_courses=catalog_courses,
    )
    await set_cached_json(cache_key, base_graph)
    return base_graph


async def get_curriculum_graph_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found"}

    degree_id = profile.get("degreeId")
    if not degree_id:
        return {"status": "degree_not_selected"}

    program_document = await catalog_repository.find_degree_program_by_id(
        database,
        str(degree_id),
    )
    if not program_document:
        return {"status": "degree_not_found"}

    academic_path = profile.get("academicPath") or {}
    track_slug = academic_path.get("trackSlug") or resolve_track_slug_from_program(
        program_document
    )
    if not track_slug:
        return {"status": "track_not_configured"}

    program_code = program_document.get("programCode") or program_code_for_track_slug(
        track_slug
    )
    if not program_code:
        return {"status": "track_not_configured"}

    catalog_year = int(program_document.get("catalogYear") or profile.get("catalogYear") or 2025)
    catalog_version = str(
        program_document.get("catalogVersion") or f"{catalog_year}-{catalog_year + 1}"
    )

    base_graph = await _load_base_graph(
        database,
        track_slug=track_slug,
        program_code=program_code,
        catalog_year=catalog_year,
        catalog_version=catalog_version,
    )
    if base_graph is None:
        return {"status": "curriculum_unavailable"}

    completed_documents = await find_all_completed_courses_by_user_id(database, user_id)
    course_ids = [
        normalize_course_id(document.get("courseId"))
        for document in completed_documents
        if document.get("courseId")
    ]
    catalog_courses = await catalog_repository.find_courses_by_ids(database, course_ids)
    courses_by_id = {
        normalize_course_id(course["_id"]): course for course in catalog_courses
    }
    completed_records = enrich_completed_records(completed_documents, courses_by_id)

    graph = overlay_transcript_on_graph(base_graph, completed_records)
    graph["academicPath"] = {
        "trackSlug": track_slug,
        "programCode": program_code,
        **{key: academic_path.get(key) for key in ("minors", "specialPrograms", "specializations")},
    }

    return {
        "status": "ok",
        "curriculumGraph": graph,
    }
