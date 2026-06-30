"""Build advisor user context and call the internal AI service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.ai_advisor_client import AiAdvisorClientError, ask_advisor
from app.config import Settings, get_settings
from app.repositories.catalog_repository import find_courses_by_ids
from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id


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


async def build_advisor_user_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    profile = await find_student_profile_by_user_id(database, user_id)
    completed_records = await find_all_completed_courses_by_user_id(database, user_id)
    course_ids = [
        str(record.get("courseId"))
        for record in completed_records
        if record.get("courseId") is not None
    ]
    catalog_courses = await find_courses_by_ids(database, course_ids)
    number_by_id = {
        str(course.get("_id")): str(course.get("number"))
        for course in catalog_courses
        if course.get("number")
    }
    completed_numbers = [
        number_by_id[str(record.get("courseId"))]
        for record in completed_records
        if record.get("courseId") is not None
        and str(record.get("courseId")) in number_by_id
    ]

    if not profile:
        return {"completed_courses": completed_numbers}

    return _json_safe_value(
        {
            "track_slug": _primary_track_slug(profile),
            "faculty": profile.get("facultyId"),
            "catalog_year": profile.get("catalogYear"),
            "completed_courses": completed_numbers,
            "display_name": profile.get("displayName"),
            "degree_id": profile.get("degreeId"),
            "plan_semester_code": profile.get("currentSemesterCode"),
        }
    )


async def ask_advisor_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    question: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    user_context = await build_advisor_user_context(database, user_id)
    try:
        raw = await ask_advisor(
            question=question,
            user_context=user_context,
            settings=settings,
        )
    except AiAdvisorClientError as exc:
        if exc.status_code == 503:
            return {"status": "unavailable", "detail": exc.detail}
        if exc.status_code == 400:
            return {"status": "bad_request", "detail": exc.detail}
        return {"status": "error", "detail": exc.detail}

    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    return {
        "status": "ok",
        "advisor": {
            "question": raw.get("question", question),
            "answer": response.get("answer", ""),
            "confidence": response.get("confidence", "medium"),
            "courseIds": response.get("course_ids", []),
            "wikiSlugs": response.get("wiki_slugs", []),
            "sources": response.get("sources", []),
            "contacts": response.get("contacts", []),
            "eligibility": response.get("eligibility"),
            "semesterResolution": raw.get("semester_resolution"),
            "retrievalStatus": (raw.get("retrieval_agent") or {}).get("status"),
        },
    }
