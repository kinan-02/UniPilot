"""MongoDB persistence for agent runs and steps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

_run_indexes_ensured = False
_step_indexes_ensured = False

RunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "requires_user_confirmation",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_id(value: Any) -> str:
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


async def ensure_agent_run_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _run_indexes_ensured
    if _run_indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_runs_collection]
    await collection.create_index(
        [("conversationId", 1), ("startedAt", -1)],
        name="agent_runs_conversation_started",
    )
    _run_indexes_ensured = True


async def ensure_agent_step_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _step_indexes_ensured
    if _step_indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_steps_collection]
    await collection.create_index([("runId", 1), ("startedAt", 1)], name="agent_steps_run_started")
    _step_indexes_ensured = True


def reset_agent_run_indexes_state() -> None:
    global _run_indexes_ensured, _step_indexes_ensured
    _run_indexes_ensured = False
    _step_indexes_ensured = False


async def create_agent_run(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    trigger_message_id: str,
    intent: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not all(
        ObjectId.is_valid(value) for value in (user_id, conversation_id, trigger_message_id)
    ):
        raise ValueError("Invalid ids for agent run")

    cfg = settings or get_settings()
    await ensure_agent_run_indexes(database, settings=cfg)
    now = _utc_now()
    document = {
        "conversationId": ObjectId(conversation_id),
        "userId": ObjectId(user_id),
        "triggerMessageId": ObjectId(trigger_message_id),
        "intent": intent,
        "status": "queued",
        "startedAt": now,
        "completedAt": None,
        "error": None,
    }
    result = await database[cfg.agent_runs_collection].insert_one(document)
    return {
        "id": str(result.inserted_id),
        "conversationId": conversation_id,
        "userId": user_id,
        "triggerMessageId": trigger_message_id,
        "intent": intent,
        "status": "queued",
        "startedAt": _iso(now),
        "completedAt": None,
        "error": None,
    }


async def complete_agent_run(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    user_id: str,
    status: RunStatus,
    intent: str | None = None,
    retrieval_profile: str | None = None,
    retrieval_metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(run_id) or not ObjectId.is_valid(user_id):
        return
    cfg = settings or get_settings()
    update: dict[str, Any] = {
        "status": status,
        "completedAt": _utc_now()
        if status in {"completed", "failed", "cancelled", "requires_user_confirmation"}
        else None,
    }
    if intent:
        update["intent"] = intent
    if retrieval_profile:
        update["retrievalProfile"] = retrieval_profile
    if retrieval_metadata:
        update["retrievalMetadata"] = retrieval_metadata
    await database[cfg.agent_runs_collection].update_one(
        {"_id": ObjectId(run_id), "userId": ObjectId(user_id)},
        {"$set": update},
    )


async def fail_agent_run(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    user_id: str,
    error: str,
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(run_id) or not ObjectId.is_valid(user_id):
        return
    cfg = settings or get_settings()
    await database[cfg.agent_runs_collection].update_one(
        {"_id": ObjectId(run_id), "userId": ObjectId(user_id)},
        {
            "$set": {
                "status": "failed",
                "error": error[:500],
                "completedAt": _utc_now(),
            }
        },
    )


async def create_agent_step(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    label: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not ObjectId.is_valid(run_id):
        raise ValueError("Invalid run id for agent step")

    cfg = settings or get_settings()
    await ensure_agent_step_indexes(database, settings=cfg)
    now = _utc_now()
    document = {
        "runId": ObjectId(run_id),
        "label": label,
        "status": "running",
        "startedAt": now,
        "completedAt": None,
        "summary": None,
    }
    result = await database[cfg.agent_steps_collection].insert_one(document)
    return {"id": str(result.inserted_id), "label": label, "status": "running"}


async def update_agent_step(
    database: AsyncIOMotorDatabase,
    *,
    step_id: str,
    status: str,
    summary: str | None = None,
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(step_id):
        return
    cfg = settings or get_settings()
    update: dict[str, Any] = {"status": status}
    if status in {"completed", "failed"}:
        update["completedAt"] = _utc_now()
    if summary:
        update["summary"] = summary[:500]
    await database[cfg.agent_steps_collection].update_one(
        {"_id": ObjectId(step_id)},
        {"$set": update},
    )
