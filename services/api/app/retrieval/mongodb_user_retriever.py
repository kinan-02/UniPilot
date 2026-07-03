"""MongoDB user-data retriever for agent context (spec §17)."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.completed_course_repository import find_all_completed_courses_by_user_id
from app.repositories.semester_plan_repository import find_semester_plans_by_user_id
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.retrieval.provenance import provenance_claim
from app.services.student_user_context_service import build_student_user_context


def _serialize_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile:
        return None
    academic_path = profile.get("academicPath") or {}
    return {
        "degreeId": str(profile.get("degreeId")) if profile.get("degreeId") else None,
        "degreeProgram": academic_path.get("trackName") or academic_path.get("trackSlug"),
        "track": academic_path.get("trackSlug"),
        "catalogYear": profile.get("catalogYear"),
        "facultyId": profile.get("facultyId"),
        "institutionId": profile.get("institutionId"),
        "currentSemesterCode": profile.get("currentSemesterCode"),
        "preferences": profile.get("preferences") or {},
    }


def _serialize_completed_courses(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for record in records:
        serialized.append(
            {
                "id": str(record.get("_id")),
                "courseId": str(record.get("courseId")) if record.get("courseId") else None,
                "semesterCode": record.get("semesterCode"),
                "grade": record.get("grade"),
                "status": record.get("status"),
            }
        )
    return serialized


async def retrieve_mongodb_user_data(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    queries: list[str],
) -> tuple[dict[str, Any], list[Any]]:
    """Return userContext fragment and provenance records for requested query keys."""
    context: dict[str, Any] = {}
    provenance: list[Any] = []
    normalized_queries = {str(item).strip() for item in queries if str(item).strip()}

    if not normalized_queries:
        return context, provenance

    need_profile = bool(
        normalized_queries
        & {
            "student_profile",
            "user_preferences",
            "degree_program",
            "track",
            "catalog_year",
        }
    )
    need_completed = "completed_courses" in normalized_queries
    need_plans = "current_semester_plans" in normalized_queries or "saved_semester_plans" in normalized_queries

    profile = await find_student_profile_by_user_id(database, user_id) if need_profile else None
    if need_profile:
        context["profile"] = _serialize_profile(profile)
        provenance.append(
            provenance_claim(
                claim="Loaded student profile",
                source_type="mongodb",
                source_id=f"student_profiles:{user_id}",
                retrieval_method="mongo_query",
                field_path="userContext.profile",
            )
        )

    if need_completed:
        summary = await build_student_user_context(database, user_id)
        completed_numbers = list(summary.get("completed_courses") or [])
        records = await find_all_completed_courses_by_user_id(database, user_id)
        context["completedCourses"] = completed_numbers
        context["completedCourseRecords"] = _serialize_completed_courses(records)
        context["completedCourseIds"] = [
            str(record.get("courseId"))
            for record in records
            if record.get("courseId") is not None
        ]
        context["dataQuality"] = summary.get("data_quality") or {}
        provenance.append(
            provenance_claim(
                claim=f"Loaded {len(completed_numbers)} completed course number(s)",
                source_type="mongodb",
                source_id=f"completed_courses:{user_id}",
                retrieval_method="mongo_query",
                confidence="high" if completed_numbers else "medium",
                field_path="userContext.completedCourses",
            )
        )

    if need_plans and ObjectId.is_valid(user_id):
        result = await find_semester_plans_by_user_id(database, user_id, limit=5)
        plans = result.get("plans") or []
        context["semesterPlans"] = []
        for plan in plans:
            primary_semester = (plan.get("semesters") or [None])[0] or {}
            context["semesterPlans"].append(
                {
                    "id": str(plan.get("_id")),
                    "name": plan.get("name"),
                    "semesterCode": primary_semester.get("semesterCode") or plan.get("semesterCode"),
                    "status": plan.get("status"),
                    "plannedCourses": primary_semester.get("plannedCourses") or plan.get("plannedCourses") or [],
                    "weeklySchedule": primary_semester.get("weeklySchedule") or plan.get("weeklySchedule"),
                }
            )
        provenance.append(
            provenance_claim(
                claim=f"Loaded {len(plans)} saved semester plan(s)",
                source_type="mongodb",
                source_id=f"semester_plans:{user_id}",
                retrieval_method="mongo_query",
                field_path="userContext.semesterPlans",
            )
        )

    if "user_preferences" in normalized_queries and profile:
        context.setdefault("profile", _serialize_profile(profile))
        context["preferences"] = (profile.get("preferences") or {}) if profile else {}

    return context, provenance
