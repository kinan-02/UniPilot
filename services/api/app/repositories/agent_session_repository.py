"""MongoDB persistence for agent sessions (API-owned creation and reads)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

_indexes_ensured = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime | Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


async def ensure_agent_session_indexes(database: AsyncIOMotorDatabase) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    settings = get_settings()
    collection = database[settings.agent_sessions_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="agent_sessions_user_created",
    )
    _indexes_ensured = True


def reset_agent_session_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


async def create_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_type: str,
    goal: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not ObjectId.is_valid(user_id):
        raise ValueError("Invalid user id for agent session")

    settings = get_settings()
    await ensure_agent_session_indexes(database)
    now = _utc_now()
    document = {
        "userId": ObjectId(user_id),
        "type": session_type,
        "goal": goal.strip(),
        "constraints": constraints or {},
        "autonomyLevel": "human_on_the_loop",
        "status": "pending",
        "finalDecision": None,
        "transcript": [],
        "rounds": 0,
        "error": None,
        "createdAt": now,
        "updatedAt": now,
    }
    result = await database[settings.agent_sessions_collection].insert_one(document)
    return {"_id": result.inserted_id, **document}


async def find_agent_session_by_id_and_user(
    database: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(session_id) or not ObjectId.is_valid(user_id):
        return None
    settings = get_settings()
    return await database[settings.agent_sessions_collection].find_one(
        {
            "_id": ObjectId(session_id),
            "userId": ObjectId(user_id),
        }
    )


async def list_agent_sessions_by_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not ObjectId.is_valid(user_id):
        return []
    settings = get_settings()
    cursor = (
        database[settings.agent_sessions_collection]
        .find({"userId": ObjectId(user_id)})
        .sort("createdAt", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def update_agent_session_by_id_and_user(
    database: AsyncIOMotorDatabase,
    session_id: str,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(session_id) or not ObjectId.is_valid(user_id):
        return None
    settings = get_settings()
    await database[settings.agent_sessions_collection].update_one(
        {"_id": ObjectId(session_id), "userId": ObjectId(user_id)},
        {"$set": updates},
    )
    return await find_agent_session_by_id_and_user(database, session_id, user_id)


def to_public_agent_session(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    approved_at = document.get("approvedAt")
    applied_at = document.get("appliedAt")
    return {
        "id": str(document["_id"]),
        "type": document.get("type"),
        "goal": document.get("goal"),
        "status": document.get("status"),
        "finalDecision": document.get("finalDecision"),
        "overriddenDecision": document.get("overriddenDecision"),
        "utilityBreakdown": document.get("utilityBreakdown"),
        "transcript": document.get("transcript") or [],
        "rounds": int(document.get("rounds") or 0),
        "error": document.get("error"),
        "approvedAt": _format_datetime(approved_at) if isinstance(approved_at, datetime) else None,
        "appliedAt": _format_datetime(applied_at) if isinstance(applied_at, datetime) else None,
        "appliedPlanId": str(document["appliedPlanId"]) if document.get("appliedPlanId") else None,
        "createdAt": _format_datetime(document.get("createdAt")),
        "updatedAt": _format_datetime(document.get("updatedAt")),
    }
