"""JWT-protected async AI job routes (AGT-1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.repositories.ai_job_repository import ensure_ai_job_indexes
from app.schemas.ai_job import CreateAiJobRequest
from app.schemas.semester_plan import OBJECT_ID_PATTERN
from app.services.ai_job_service import create_job_for_user, get_job_for_user, list_jobs_for_user

router = APIRouter(prefix="/ai/jobs", tags=["ai-jobs"])

_ai_job_indexes_ready = False

ALLOWED_STATUSES = frozenset({"pending", "processing", "completed", "failed"})


def reset_ai_job_indexes_state() -> None:
    global _ai_job_indexes_ready
    _ai_job_indexes_ready = False


async def _ensure_ai_job_indexes_once() -> None:
    global _ai_job_indexes_ready

    if _ai_job_indexes_ready:
        return

    database = await get_database()
    await ensure_ai_job_indexes(database)
    _ai_job_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def _validate_job_id(job_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")
    return job_id


@router.post("", status_code=202)
async def create_ai_job_route(
    request: Request,
    payload: CreateAiJobRequest,
    auth: AuthContext = Depends(require_auth),
) -> JSONResponse:
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_ai_job_indexes_once()
    database = await get_database()
    result = await create_job_for_user(database, auth.user_id, payload)
    return JSONResponse(status_code=202, content=success_response(result))


@router.get("")
async def list_ai_jobs_route(
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    if status is not None and status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid job status filter")

    await _ensure_ai_job_indexes_once()
    database = await get_database()
    data = await list_jobs_for_user(
        database,
        auth.user_id,
        page=page,
        limit=limit,
        status=status,
    )
    return success_response(data)


@router.get("/{job_id}")
async def get_ai_job_route(
    job_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_ai_job_indexes_once()
    job_id = _validate_job_id(job_id)
    database = await get_database()
    result = await get_job_for_user(database, auth.user_id, job_id)
    if not result:
        raise HTTPException(status_code=404, detail="AI job not found")
    return success_response(result)
