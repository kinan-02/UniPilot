"""Load and enrich per-student context for MAS sessions."""

from __future__ import annotations

import logging
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.session_bootstrap_client import fetch_session_bootstrap_for_user
from app.clients.semester_suggestion_client import fetch_semester_suggestion_for_user
from app.clients.student_user_context_client import fetch_student_user_context_for_user
from app.config import Settings, get_settings
from app.effectors.gateway import get_effector_gateway
from app.services.path_relevant_planner import enrich_user_context_with_graduation_path
from app.services.plan_progress import _normalize_course_number
from app.services.plan_risk import resolve_max_credits
from app.services.user_data_quality import append_data_quality_warning
from app.user_context import build_user_context

logger = logging.getLogger(__name__)

ContextSource = Literal["api_bootstrap", "api_split", "mongo_fallback"]


def _attach_graduation(
    user_context: dict[str, Any],
    *,
    graduation_progress: dict[str, Any] | None,
    graduation_error: str | None,
) -> dict[str, Any]:
    if isinstance(graduation_progress, dict):
        updated = {**user_context, "graduation_progress": graduation_progress}
        return enrich_user_context_with_graduation_path(updated)
    return append_data_quality_warning(
        user_context,
        graduation_error or "graduation_unavailable",
    )


def _apply_progress_planning_bundle(
    user_context: dict[str, Any],
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    """Override transcript and path priorities with Progress-page-aligned bootstrap data."""
    updated = dict(user_context)
    planning = bootstrap.get("planningContext")
    if isinstance(planning, dict) and planning.get("status") == "ok":
        updated["completed_courses"] = list(planning.get("transcriptCourseNumbers") or [])
        updated["path_priority_courses"] = list(planning.get("pathPriorityCourseNumbers") or [])
        updated["planning_context"] = planning
        updated["planning_source"] = "progress_bundle"

    if "planningReady" in bootstrap:
        updated["planning_ready"] = bool(bootstrap.get("planningReady"))

    curriculum_graph = bootstrap.get("curriculumGraph")
    if isinstance(curriculum_graph, dict):
        updated["curriculum_graph"] = curriculum_graph

    curriculum_error = bootstrap.get("curriculumError")
    if isinstance(curriculum_error, str) and curriculum_error.strip():
        updated = append_data_quality_warning(updated, curriculum_error)

    return updated


async def _attach_api_semester_catalog(
    user_context: dict[str, Any],
    user_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Attach Mongo catalog semester suggestions when Progress planning bundle is active."""
    if user_context.get("planning_source") != "progress_bundle":
        return user_context
    if not user_context.get("planning_ready"):
        return user_context

    semester_code = str(user_context.get("plan_semester_code") or "").strip()
    if not semester_code:
        return user_context

    result = await fetch_semester_suggestion_for_user(
        user_id=user_id,
        semester_code=semester_code,
        max_credits=resolve_max_credits(user_context),
        settings=settings,
    )
    if not isinstance(result, dict) or result.get("status") != "ok":
        return append_data_quality_warning(user_context, "api_catalog_unavailable")

    updated = dict(user_context)
    updated["api_semester_catalog"] = result
    updated["catalog_source"] = "api_mongo"

    suggested: list[str] = []
    credits_map: dict[str, float] = {}
    for course in result.get("plannedCourses") or []:
        if not isinstance(course, dict):
            continue
        number = _normalize_course_number(str(course.get("courseNumber") or course.get("number") or ""))
        if not number:
            continue
        suggested.append(number)
        raw_credits = course.get("credits")
        if raw_credits is not None:
            try:
                credits_map[number] = float(raw_credits)
            except (TypeError, ValueError):
                pass

    updated["api_suggested_course_numbers"] = list(dict.fromkeys(suggested))
    updated["api_course_credits"] = credits_map
    return updated


async def _load_from_api_bootstrap(
    user_id: str,
    *,
    settings: Settings,
) -> tuple[dict[str, Any], ContextSource] | None:
    bootstrap = await fetch_session_bootstrap_for_user(user_id=user_id, settings=settings)
    if not isinstance(bootstrap, dict):
        return None

    user_context = dict(bootstrap["userContext"])
    user_context["context_source"] = "api_bootstrap"
    graduation_progress = bootstrap.get("graduationProgress")
    graduation_error = bootstrap.get("graduationError")
    if not isinstance(graduation_progress, dict) and isinstance(graduation_error, str):
        user_context = _attach_graduation(
            user_context,
            graduation_progress=None,
            graduation_error=graduation_error,
        )
    else:
        user_context = _attach_graduation(
            user_context,
            graduation_progress=graduation_progress if isinstance(graduation_progress, dict) else None,
            graduation_error=None,
        )
    user_context = _apply_progress_planning_bundle(user_context, bootstrap)
    return user_context, "api_bootstrap"


async def _load_from_api_split(
    user_id: str,
    *,
    settings: Settings,
) -> tuple[dict[str, Any], ContextSource] | None:
    api_context = await fetch_student_user_context_for_user(user_id=user_id, settings=settings)
    if not isinstance(api_context, dict):
        return None

    user_context = {**api_context, "context_source": "api_split"}
    graduation_progress, graduation_error = await get_effector_gateway().fetch_graduation_progress_with_meta(
        user_id=user_id,
        settings=settings,
    )
    user_context = _attach_graduation(
        user_context,
        graduation_progress=graduation_progress,
        graduation_error=graduation_error,
    )
    return user_context, "api_split"


async def _load_from_mongo_fallback(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    settings: Settings,
) -> tuple[dict[str, Any], ContextSource]:
    logger.warning(
        "Falling back to direct Mongo user context for user_id=%s (API unavailable)",
        user_id,
    )
    user_context = await build_user_context(database, user_id)
    user_context = {**user_context, "context_source": "mongo_fallback"}
    graduation_progress, graduation_error = await get_effector_gateway().fetch_graduation_progress_with_meta(
        user_id=user_id,
        settings=settings,
    )
    user_context = _attach_graduation(
        user_context,
        graduation_progress=graduation_progress,
        graduation_error=graduation_error,
    )
    return user_context, "mongo_fallback"


async def load_enriched_user_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    constraints: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Load canonical student context from API (Mongo fallback) and merge graduation progress."""
    cfg = settings or get_settings()

    loaded = await _load_from_api_bootstrap(user_id, settings=cfg)
    if loaded is None:
        loaded = await _load_from_api_split(user_id, settings=cfg)
    if loaded is None:
        loaded = await _load_from_mongo_fallback(database, user_id, settings=cfg)

    user_context, _source = loaded
    if constraints:
        user_context = {**user_context, "constraints": constraints}
    user_context = await _attach_api_semester_catalog(user_context, user_id, settings=cfg)
    return user_context
