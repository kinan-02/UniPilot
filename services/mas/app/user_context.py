"""Load per-student context from MongoDB (not institutional ground truth)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.completed_course_transcript import (
    course_number_from_catalog_document,
    extract_effective_completed_course_numbers,
)
from app.services.track_registry import resolve_track_slug_from_program
from app.services.user_data_quality import (
    MAX_COMPLETED_RECORDS,
    build_profile_quality_warnings,
    build_transcript_quality_warnings,
    merge_data_quality,
    normalize_completed_course_numbers,
)

COMPLETED_COURSES_COLLECTION = "completed_courses"
STUDENT_PROFILES_COLLECTION = "student_profiles"
COURSES_COLLECTION = "courses"
DEGREE_PROGRAMS_COLLECTION = "degree_programs"
PUBLISHED_STATUS_FILTER = {"status": "published"}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


def _primary_track_slug(profile: dict[str, Any] | None) -> str | None:
    if not profile:
        return None
    academic_path = profile.get("academicPath") or {}
    track_slug = academic_path.get("trackSlug")
    if isinstance(track_slug, str) and track_slug.strip():
        return track_slug.strip()
    return None


async def _find_degree_program(
    database: AsyncIOMotorDatabase,
    degree_id: str,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(degree_id):
        return None
    return await database[DEGREE_PROGRAMS_COLLECTION].find_one(
        {**PUBLISHED_STATUS_FILTER, "_id": ObjectId(degree_id)}
    )


async def _resolve_track_slug(
    database: AsyncIOMotorDatabase,
    profile: dict[str, Any],
) -> str | None:
    explicit = _primary_track_slug(profile)
    if explicit:
        return explicit

    degree_id = profile.get("degreeId")
    if degree_id is None:
        return None

    program = await _find_degree_program(database, str(degree_id))
    inferred = resolve_track_slug_from_program(program)
    if isinstance(inferred, str) and inferred.strip():
        return inferred.strip()
    return None


async def build_user_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    parsed_user_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else None
    if parsed_user_id is None:
        return {"user_id": user_id, "completed_courses": []}

    profile = await database[STUDENT_PROFILES_COLLECTION].find_one({"userId": parsed_user_id})
    completed_records = (
        await database[COMPLETED_COURSES_COLLECTION]
        .find({"userId": parsed_user_id})
        .to_list(length=MAX_COMPLETED_RECORDS)
    )

    course_ids = [
        str(record.get("courseId"))
        for record in completed_records
        if record.get("courseId") is not None
    ]
    unique_course_ids = len(set(course_ids))
    object_ids = [ObjectId(course_id) for course_id in course_ids if ObjectId.is_valid(course_id)]
    catalog_courses = (
        await database[COURSES_COLLECTION]
        .find({"_id": {"$in": object_ids}})
        .to_list(length=MAX_COMPLETED_RECORDS)
        if object_ids
        else []
    )
    number_by_id: dict[str, str] = {}
    for course in catalog_courses:
        course_id = str(course.get("_id"))
        number = course_number_from_catalog_document(course)
        if number:
            number_by_id[course_id] = number

    completed_numbers = normalize_completed_course_numbers(
        extract_effective_completed_course_numbers(
            completed_records,
            number_by_course_id=number_by_id,
        )
    )
    unresolved_course_count = sum(1 for course_id in set(course_ids) if course_id not in number_by_id)
    track_slug = await _resolve_track_slug(database, profile) if profile else None
    data_quality = merge_data_quality(
        build_transcript_quality_warnings(
            completed_record_count=len(completed_records),
            resolved_completed_count=len(completed_numbers),
            unresolved_course_count=unresolved_course_count,
            truncated=len(completed_records) >= MAX_COMPLETED_RECORDS,
        ),
        build_profile_quality_warnings(profile, track_slug=track_slug),
    )

    if not profile:
        return _json_safe_value(
            {
                "user_id": user_id,
                "completed_courses": completed_numbers,
                "data_quality": data_quality,
                "transcript_stats": {
                    "recordCount": len(completed_records),
                    "uniqueCourseCount": unique_course_ids,
                    "resolvedCompletedCount": len(completed_numbers),
                },
            }
        )

    return _json_safe_value(
        {
            "user_id": user_id,
            "track_slug": track_slug,
            "faculty": profile.get("facultyId"),
            "catalog_year": profile.get("catalogYear"),
            "completed_courses": completed_numbers,
            "display_name": profile.get("displayName"),
            "degree_id": profile.get("degreeId"),
            "plan_semester_code": profile.get("currentSemesterCode"),
            "preferences": profile.get("preferences") or {},
            "data_quality": data_quality,
            "transcript_stats": {
                "recordCount": len(completed_records),
                "uniqueCourseCount": unique_course_ids,
                "resolvedCompletedCount": len(completed_numbers),
            },
        }
    )
