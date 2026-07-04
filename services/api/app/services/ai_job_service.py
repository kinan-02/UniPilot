"""Create, enqueue, query, and process async AI jobs."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.ai_job_repository import (
    create_ai_job,
    find_ai_job_for_user,
    list_ai_jobs_for_user,
    mark_ai_job_completed,
    mark_ai_job_failed,
    mark_ai_job_processing,
    to_public_ai_job,
)
from app.schemas.ai_job import CreateAiJobRequest
from app.services.ai_job_handlers import dispatch_ai_job_handler
from app.services.ai_job_queue import enqueue_ai_job


async def create_job_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    request: CreateAiJobRequest,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = await create_ai_job(
        database,
        user_id,
        job_type=request.type,
        payload=request.payload,
        settings=settings,
    )
    job_id = str(document["_id"])
    await enqueue_ai_job(job_id, settings=settings)
    public = to_public_ai_job(document)
    return {"status": "queued", "job": public}


async def get_job_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    job_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    document = await find_ai_job_for_user(
        database,
        user_id,
        job_id,
        settings=settings,
    )
    public = to_public_ai_job(document)
    if not public:
        return None
    return {"job": public}


async def list_jobs_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    result = await list_ai_jobs_for_user(
        database,
        user_id,
        page=page,
        limit=limit,
        status=status,
        settings=settings,
    )
    jobs = [
        item for item in (to_public_ai_job(doc) for doc in result["jobs"]) if item is not None
    ]
    return {
        "jobs": jobs,
        "pagination": {
            "total": result["total"],
            "page": result["page"],
            "limit": result["limit"],
        },
    }


async def process_job_by_id(
    database: AsyncIOMotorDatabase,
    job_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Worker entrypoint: pending → processing → completed/failed."""
    settings = settings or get_settings()
    processing = await mark_ai_job_processing(database, job_id, settings=settings)
    if not processing:
        from app.repositories.ai_job_repository import find_ai_job_by_id

        existing = await find_ai_job_by_id(database, job_id, settings=settings)
        if not existing:
            return {"status": "not_found"}
        return {"status": "skipped", "jobStatus": existing.get("status")}

    user_id = str(processing["userId"])
    job_type = str(processing.get("type") or "")
    payload = processing.get("payload") or {}

    try:
        result = await dispatch_ai_job_handler(
            database,
            job_type=job_type,
            user_id=user_id,
            payload=payload,
            settings=settings,
            job_id=job_id,
        )
        completed = await mark_ai_job_completed(
            database,
            job_id,
            result,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 — persist failure on job document
        await mark_ai_job_failed(database, job_id, str(exc), settings=settings)
        return {"status": "failed", "error": str(exc)}

    public = to_public_ai_job(completed)
    return {"status": "completed", "job": public}
