"""JWT-protected AI recommendation routes (AGT-8)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.repositories.ai_recommendation_repository import (
    dismiss_ai_recommendation_for_user,
    ensure_ai_recommendation_indexes,
    list_ai_recommendations_for_user,
    to_public_ai_recommendation,
)
from app.schemas.semester_plan import OBJECT_ID_PATTERN

router = APIRouter(prefix="/ai/recommendations", tags=["ai-recommendations"])

_recommendation_indexes_ready = False


def reset_recommendation_indexes_state() -> None:
    global _recommendation_indexes_ready
    _recommendation_indexes_ready = False


async def _ensure_recommendation_indexes_once() -> None:
    global _recommendation_indexes_ready

    if _recommendation_indexes_ready:
        return

    database = await get_database()
    await ensure_ai_recommendation_indexes(database)
    _recommendation_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.get("")
async def list_recommendations_route(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    status: str = Query(default="active"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request)
    await _ensure_recommendation_indexes_once()

    database = await get_database()
    result = await list_ai_recommendations_for_user(
        database,
        auth.user_id,
        status=status,
        page=page,
        limit=limit,
    )
    recommendations = [
        item
        for item in (to_public_ai_recommendation(doc) for doc in result["recommendations"])
        if item is not None
    ]
    return success_response(
        {
            "recommendations": recommendations,
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "limit": result["limit"],
            },
        }
    )


@router.post("/{recommendation_id}/dismiss")
async def dismiss_recommendation_route(
    request: Request,
    recommendation_id: str,
    auth: AuthContext = Depends(require_auth),
) -> JSONResponse:
    await enforce_ai_rate_limit(request)
    await _ensure_recommendation_indexes_once()

    if not OBJECT_ID_PATTERN.fullmatch(recommendation_id):
        raise HTTPException(status_code=400, detail="Invalid recommendation id")

    database = await get_database()
    dismissed = await dismiss_ai_recommendation_for_user(
        database,
        auth.user_id,
        recommendation_id,
    )
    if not dismissed:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    public = to_public_ai_recommendation(dismissed)
    return JSONResponse(content=success_response({"recommendation": public}))
