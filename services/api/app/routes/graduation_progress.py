"""Graduation progress route (Phase 15)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_progress_rate_limit
from app.security.impersonation_guard import reject_impersonation_query_params
from app.services.curriculum_graph_service import get_curriculum_graph_for_user
from app.services.graduation_progress_service import get_graduation_progress_for_user

router = APIRouter(prefix="/graduation-progress", tags=["graduation-progress"])


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.get("")
async def get_graduation_progress(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    reject_impersonation_query_params(request)
    await enforce_progress_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await get_graduation_progress_for_user(database, auth.user_id)

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")

    if result["status"] == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail=(
                "A degree must be selected on the student profile before "
                "graduation progress can be calculated"
            ),
        )

    if result["status"] == "degree_not_found":
        raise HTTPException(
            status_code=400,
            detail="Referenced degree was not found in the catalog",
        )

    return success_response({"graduationProgress": result["progress"]})


@router.get("/curriculum-graph")
async def get_curriculum_graph(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    reject_impersonation_query_params(request)
    await enforce_progress_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await get_curriculum_graph_for_user(database, auth.user_id)

    if result["status"] == "profile_not_found":
        raise HTTPException(status_code=404, detail="Student profile not found")

    if result["status"] == "degree_not_selected":
        raise HTTPException(
            status_code=400,
            detail=(
                "A degree must be selected on the student profile before "
                "the curriculum graph can be loaded"
            ),
        )

    if result["status"] == "degree_not_found":
        raise HTTPException(
            status_code=400,
            detail="Referenced degree was not found in the catalog",
        )

    if result["status"] == "track_not_configured":
        raise HTTPException(
            status_code=400,
            detail="Academic track is not configured for this degree program",
        )

    if result["status"] == "curriculum_unavailable":
        raise HTTPException(
            status_code=404,
            detail="No semester-matrix curriculum is available for this track",
        )

    return success_response({"curriculumGraph": result["curriculumGraph"]})
