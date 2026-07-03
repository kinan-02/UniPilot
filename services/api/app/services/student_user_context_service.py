"""Canonical per-student context for advisor and internal MAS integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.track_registry import resolve_track_slug_from_program
from app.planning.prerequisite_resolver import canonical_course_number
from app.repositories.catalog_repository import (
    course_summary_from_document,
    find_courses_by_ids,
    find_degree_program_by_id,
)
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.graduation_progress_calculator import build_effective_completions

MAX_COMPLETED_RECORDS = 10_000


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


def normalize_completed_course_numbers(numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in numbers:
        value = canonical_course_number(str(raw))
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def build_transcript_quality_warnings(
    *,
    completed_record_count: int,
    resolved_completed_count: int,
    unresolved_course_count: int,
    truncated: bool,
) -> list[str]:
    warnings: list[str] = []
    if truncated:
        warnings.append("transcript_truncated")
    if completed_record_count == 0:
        warnings.append("no_transcript_records")
    elif resolved_completed_count == 0:
        warnings.append("transcript_unresolved")
    elif unresolved_course_count > 0:
        warnings.append("transcript_partial_resolution")
    return warnings


def build_profile_quality_warnings(
    profile: dict[str, Any] | None,
    *,
    track_slug: str | None = None,
) -> list[str]:
    if not profile:
        return ["profile_not_found"]
    warnings: list[str] = []
    if not profile.get("degreeId"):
        warnings.append("degree_not_selected")
    if not (isinstance(track_slug, str) and track_slug.strip()):
        warnings.append("track_not_set")
    return warnings


def merge_data_quality(*warning_lists: list[str]) -> dict[str, Any]:
    warnings = sorted({warning for group in warning_lists for warning in group})
    return {"warnings": warnings, "ok": len(warnings) == 0}


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

    program = await find_degree_program_by_id(database, str(degree_id))
    inferred = resolve_track_slug_from_program(program)
    if isinstance(inferred, str) and inferred.strip():
        return inferred.strip()
    return None


async def build_student_user_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    """Load profile + effective transcript completions with data-quality metadata."""
    if not ObjectId.is_valid(user_id):
        return {"user_id": user_id, "completed_courses": []}

    profile = await find_student_profile_by_user_id(database, user_id)
    completed_records = await find_all_completed_courses_by_user_id(database, user_id)
    truncated = len(completed_records) >= MAX_COMPLETED_RECORDS

    effective_completions = build_effective_completions(completed_records)
    course_ids = list(effective_completions.keys())
    unique_course_ids = len(set(course_ids))
    catalog_courses = await find_courses_by_ids(database, course_ids)

    number_by_id: dict[str, str] = {}
    for course in catalog_courses:
        summary = course_summary_from_document(course)
        if not summary:
            continue
        number = canonical_course_number(summary.get("number"))
        if number:
            number_by_id[str(course.get("_id"))] = number

    completed_numbers = normalize_completed_course_numbers(
        [number_by_id[course_id] for course_id in course_ids if course_id in number_by_id]
    )
    unresolved_course_count = sum(1 for course_id in set(course_ids) if course_id not in number_by_id)
    track_slug = await _resolve_track_slug(database, profile) if profile else None
    data_quality = merge_data_quality(
        build_transcript_quality_warnings(
            completed_record_count=len(completed_records),
            resolved_completed_count=len(completed_numbers),
            unresolved_course_count=unresolved_course_count,
            truncated=truncated,
        ),
        build_profile_quality_warnings(profile, track_slug=track_slug),
    )
    transcript_stats = {
        "recordCount": len(completed_records),
        "uniqueCourseCount": unique_course_ids,
        "resolvedCompletedCount": len(completed_numbers),
    }

    if not profile:
        return _json_safe_value(
            {
                "user_id": user_id,
                "completed_courses": completed_numbers,
                "data_quality": data_quality,
                "transcript_stats": transcript_stats,
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
            "transcript_stats": transcript_stats,
        }
    )
