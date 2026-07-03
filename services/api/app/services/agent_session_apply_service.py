"""Apply MAS agent session decisions to semester plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.technion_planner_semesters import plan_semester_code_from_course_json_filename
from app.repositories import catalog_repository
from app.repositories.agent_session_repository import (
    find_agent_session_by_id_and_user,
    to_public_agent_session,
    update_agent_session_by_id_and_user,
)
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.manual_semester_plan_service import create_manual_semester_plan
from app.services.semester_plan_suggestion_service import suggest_semester_schedule


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _effective_decision(session: dict[str, Any]) -> dict[str, Any] | None:
    override = session.get("overriddenDecision")
    if isinstance(override, dict) and override.get("course_ids"):
        return override
    final_decision = session.get("finalDecision")
    return final_decision if isinstance(final_decision, dict) else None


def _resolve_semester_code(
    decision: dict[str, Any],
    profile: dict[str, Any] | None,
) -> str | None:
    profile_code = str((profile or {}).get("currentSemesterCode") or "").strip()
    if profile_code:
        return profile_code

    explicit = decision.get("planSemesterCode")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    filename = decision.get("semester_filename")
    if isinstance(filename, str) and filename.strip():
        return plan_semester_code_from_course_json_filename(filename.strip())
    schedule = decision.get("schedule")
    if isinstance(schedule, dict):
        code = schedule.get("planSemesterCode")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


async def approve_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}
    if session.get("status") != "completed":
        return {"status": "invalid_state", "error": "Session must be completed before approval."}
    if not _effective_decision(session):
        return {"status": "invalid_state", "error": "Session has no decision to approve."}

    now = _utc_now()
    updated = await update_agent_session_by_id_and_user(
        database,
        session_id,
        user_id,
        {
            "approvedAt": now,
            "approvedBy": ObjectId(user_id),
            "updatedAt": now,
        },
    )
    if updated is None:
        return {"status": "not_found"}
    public = to_public_agent_session(updated)
    return {"status": "ok", "session": public}


async def override_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
    course_ids: list[str],
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}
    if session.get("status") != "completed":
        return {"status": "invalid_state", "error": "Only completed sessions can be overridden."}

    normalized = [str(course_id).strip() for course_id in course_ids if str(course_id).strip()]
    if not normalized:
        return {"status": "validation_error", "errors": ["At least one course id is required."]}

    base = dict(session.get("finalDecision") or {})
    base["course_ids"] = list(dict.fromkeys(normalized))
    now = _utc_now()
    updated = await update_agent_session_by_id_and_user(
        database,
        session_id,
        user_id,
        {
            "overriddenDecision": base,
            "approvedAt": None,
            "approvedBy": None,
            "updatedAt": now,
        },
    )
    if updated is None:
        return {"status": "not_found"}
    public = to_public_agent_session(updated)
    return {"status": "ok", "session": public}


async def apply_agent_session_to_plan(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
    plan_name: str | None = None,
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}
    if session.get("status") != "completed":
        return {"status": "invalid_state", "error": "Session must be completed before apply."}
    if session.get("appliedPlanId"):
        return {
            "status": "already_applied",
            "error": "This session was already applied to a semester plan.",
            "planId": str(session["appliedPlanId"]),
        }
    if not session.get("approvedAt"):
        return {
            "status": "approval_required",
            "error": "Approve the recommendation before applying it to a semester plan.",
        }

    decision = _effective_decision(session)
    if decision is None:
        return {"status": "invalid_state", "error": "Session has no final decision."}

    course_numbers = [
        str(course_id).strip()
        for course_id in (decision.get("course_ids") or [])
        if str(course_id).strip()
    ]
    if not course_numbers:
        return {"status": "validation_error", "errors": ["Decision has no courses to apply."]}

    profile = await find_student_profile_by_user_id(database, user_id)
    semester_code = _resolve_semester_code(decision, profile)
    if not semester_code:
        return {"status": "validation_error", "errors": ["Could not resolve target semester code."]}

    catalog_courses = await catalog_repository.find_courses_by_numbers(database, course_numbers)
    by_number = {
        str(course.get("courseNumber") or ""): course
        for course in catalog_courses
        if course.get("courseNumber")
    }
    missing = [number for number in course_numbers if number not in by_number]
    if missing:
        return {
            "status": "validation_error",
            "errors": [f"Catalog courses not found for: {', '.join(missing)}"],
        }

    goal = str(session.get("goal") or "MAS recommendation")
    planned_courses: list[dict[str, Any]] = []
    for number in course_numbers:
        course = by_number[number]
        planned_courses.append(
            {
                "courseId": str(course["_id"]),
                "courseNumber": number,
                "courseTitle": str(course.get("titleHebrew") or course.get("title") or ""),
                "credits": float(course.get("credits") or 0),
                "category": "mas",
                "reason": goal[:240],
                "isActive": True,
            }
        )

    schedule_result = await suggest_semester_schedule(
        database,
        user_id,
        semester_code=semester_code,
        planned_courses=planned_courses,
    )
    selections_by_number: dict[str, list[dict[str, Any]]] = {}
    skipped_from_schedule: list[dict[str, Any]] = []
    if schedule_result.get("status") == "ok":
        selections_by_number = {
            str(item.get("courseNumber") or ""): item.get("selectedLessonEvents") or []
            for item in schedule_result.get("selections") or []
        }
        skipped_from_schedule = list(schedule_result.get("skippedCourses") or [])
    else:
        skipped_from_schedule.append(
            {
                "reason": (
                    "; ".join(schedule_result.get("errors") or [])
                    or str(schedule_result.get("status") or "schedule_suggestion_failed")
                ),
            }
        )

    for planned in planned_courses:
        number = str(planned.get("courseNumber") or "")
        events = selections_by_number.get(number)
        if events:
            planned["selectedLessonEvents"] = events

    create_payload = {
        "name": (plan_name or f"MAS: {goal[:80]}").strip(),
        "status": "draft",
        "semesterCode": semester_code,
        "plannedCourses": [
            {
                "courseId": planned["courseId"],
                "category": planned.get("category"),
                "reason": planned.get("reason"),
                "isActive": True,
                "selectedLessonEvents": planned.get("selectedLessonEvents"),
            }
            for planned in planned_courses
        ],
    }
    create_result = await create_manual_semester_plan(database, user_id, create_payload)
    if create_result.get("status") != "ok":
        return create_result

    plan = create_result["plan"]
    plan_id = str(plan["_id"])
    now = _utc_now()
    updated = await update_agent_session_by_id_and_user(
        database,
        session_id,
        user_id,
        {
            "appliedPlanId": ObjectId(plan_id),
            "appliedAt": now,
            "updatedAt": now,
        },
    )
    public_session = to_public_agent_session(updated) if updated else to_public_agent_session(session)
    return {
        "status": "ok",
        "session": public_session,
        "semesterPlanId": plan_id,
        "skippedCourses": skipped_from_schedule,
    }
