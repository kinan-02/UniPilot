"""Single-call MAS session bootstrap: profile, transcript, graduation progress."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.curriculum_graph_service import get_curriculum_graph_for_user
from app.services.graduation_progress_service import get_graduation_progress_for_user
from app.services.planning_context_service import build_planning_context
from app.services.student_user_context_service import build_student_user_context

GRADUATION_WARNING_BY_STATUS: dict[str, str] = {
    "profile_not_found": "profile_not_found",
    "degree_not_selected": "degree_not_selected",
    "degree_not_found": "degree_not_found",
}

CURRICULUM_WARNING_BY_STATUS: dict[str, str] = {
    "profile_not_found": "profile_not_found",
    "degree_not_selected": "degree_not_selected",
    "degree_not_found": "degree_not_found",
    "track_not_configured": "track_not_set",
    "curriculum_unavailable": "graduation_unavailable",
}


async def build_session_bootstrap_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    """
    Return Progress-aligned planning context in one payload.

    Graduation/curriculum failures are structured (not HTTP errors) so MAS can
    surface data-quality warnings while still returning profile context.
    """
    user_context = await build_student_user_context(database, user_id)
    graduation_result = await get_graduation_progress_for_user(database, user_id)
    curriculum_result = await get_curriculum_graph_for_user(database, user_id)

    graduation_status = str(graduation_result.get("status") or "unknown")
    curriculum_status = str(curriculum_result.get("status") or "unknown")

    graduation_progress = (
        graduation_result["progress"] if graduation_status == "ok" else None
    )
    curriculum_graph = (
        curriculum_result["curriculumGraph"] if curriculum_status == "ok" else None
    )

    planning_context = build_planning_context(
        graduation_progress=graduation_progress,
        curriculum_graph=curriculum_graph,
    )

    payload: dict[str, Any] = {
        "userContext": user_context,
        "graduationProgress": graduation_progress,
        "graduationStatus": graduation_status,
        "graduationError": None,
        "curriculumGraph": curriculum_graph,
        "curriculumStatus": curriculum_status,
        "curriculumError": None,
        "planningContext": planning_context,
        "planningReady": graduation_status == "ok" and planning_context.get("status") == "ok",
    }

    if graduation_status != "ok":
        payload["graduationError"] = GRADUATION_WARNING_BY_STATUS.get(
            graduation_status,
            "graduation_unavailable",
        )

    if curriculum_status != "ok":
        payload["curriculumError"] = CURRICULUM_WARNING_BY_STATUS.get(
            curriculum_status,
            "graduation_unavailable",
        )

    return payload
