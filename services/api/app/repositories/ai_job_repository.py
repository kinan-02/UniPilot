"""MongoDB repository for async AI jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.semester_plan_repository import parse_object_id

AiJobStatus = Literal["pending", "processing", "completed", "failed"]


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def ensure_ai_job_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.ai_jobs_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="ai_jobs_user_created_at",
    )
    await collection.create_index(
        [("userId", 1), ("status", 1), ("createdAt", -1)],
        name="ai_jobs_user_status_created_at",
    )


def build_ai_job_document(
    user_id: str,
    *,
    job_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for AI job")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "type": job_type,
        "status": "pending",
        "payload": payload,
        "result": None,
        "error": None,
        "createdAt": now,
        "updatedAt": now,
        "startedAt": None,
        "finishedAt": None,
    }


async def create_ai_job(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    job_type: str,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_ai_job_document(user_id, job_type=job_type, payload=payload)
    insert_result = await database[settings.ai_jobs_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def find_ai_job_by_id(
    database: AsyncIOMotorDatabase,
    job_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_job_id = parse_object_id(job_id)
    if parsed_job_id is None:
        return None
    return await database[settings.ai_jobs_collection].find_one({"_id": parsed_job_id})


async def find_ai_job_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    job_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_job_id = parse_object_id(job_id)
    if parsed_user_id is None or parsed_job_id is None:
        return None
    return await database[settings.ai_jobs_collection].find_one(
        {"_id": parsed_job_id, "userId": parsed_user_id}
    )


async def list_ai_jobs_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return {"jobs": [], "total": 0, "page": 1, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 50)
    skip = (safe_page - 1) * safe_limit
    query: dict[str, Any] = {"userId": parsed_user_id}
    if status:
        query["status"] = status

    collection = database[settings.ai_jobs_collection]
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("createdAt", -1).skip(skip).limit(safe_limit)
    jobs = [doc async for doc in cursor]
    return {"jobs": jobs, "total": total, "page": safe_page, "limit": safe_limit}


async def mark_ai_job_processing(
    database: AsyncIOMotorDatabase,
    job_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_job_id = parse_object_id(job_id)
    if parsed_job_id is None:
        return None

    now = datetime.now(timezone.utc)
    return await database[settings.ai_jobs_collection].find_one_and_update(
        {"_id": parsed_job_id, "status": "pending"},
        {
            "$set": {
                "status": "processing",
                "updatedAt": now,
                "startedAt": now,
            }
        },
        return_document=True,
    )


async def mark_ai_job_completed(
    database: AsyncIOMotorDatabase,
    job_id: str,
    result: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_job_id = parse_object_id(job_id)
    if parsed_job_id is None:
        return None

    now = datetime.now(timezone.utc)
    return await database[settings.ai_jobs_collection].find_one_and_update(
        {"_id": parsed_job_id, "status": "processing"},
        {
            "$set": {
                "status": "completed",
                "result": result,
                "error": None,
                "updatedAt": now,
                "finishedAt": now,
            }
        },
        return_document=True,
    )


async def mark_ai_job_failed(
    database: AsyncIOMotorDatabase,
    job_id: str,
    error: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_job_id = parse_object_id(job_id)
    if parsed_job_id is None:
        return None

    now = datetime.now(timezone.utc)
    return await database[settings.ai_jobs_collection].find_one_and_update(
        {"_id": parsed_job_id, "status": {"$in": ["pending", "processing"]}},
        {
            "$set": {
                "status": "failed",
                "error": error[:2000],
                "updatedAt": now,
                "finishedAt": now,
            }
        },
        return_document=True,
    )


def to_public_ai_job(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None

    return {
        "id": str(document["_id"]),
        "type": document.get("type"),
        "status": document.get("status"),
        "payload": document.get("payload") or {},
        "result": document.get("result"),
        "error": document.get("error"),
        "createdAt": _format_datetime(document.get("createdAt")),
        "updatedAt": _format_datetime(document.get("updatedAt")),
        "startedAt": _format_datetime(document.get("startedAt")),
        "finishedAt": _format_datetime(document.get("finishedAt")),
    }
