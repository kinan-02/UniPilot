"""Internal routes for worker → API job processing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.db.mongo import get_database
from app.dependencies.internal_auth import require_internal_service_token
from app.repositories.ai_job_repository import ensure_ai_job_indexes
from app.routes.ai_jobs import _validate_job_id, success_response
from app.services.ai_job_service import process_job_by_id

router = APIRouter(prefix="/internal/ai-jobs", tags=["internal-ai-jobs"])


async def _ensure_indexes() -> None:
    database = await get_database()
    await ensure_ai_job_indexes(database)


@router.post("/{job_id}/process", dependencies=[Depends(require_internal_service_token)])
async def process_ai_job_route(job_id: str) -> dict[str, Any]:
    job_id = _validate_job_id(job_id)
    await _ensure_indexes()
    database = await get_database()
    result = await process_job_by_id(database, job_id)

    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="AI job not found")

    return success_response(result)
