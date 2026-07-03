"""MongoDB persistence for agent tool calls (spec §27.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

_indexes_ensured = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_id(value: Any) -> str:
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


async def ensure_agent_tool_call_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_tool_calls_collection]
    await collection.create_index([("runId", 1), ("createdAt", 1)], name="agent_tool_calls_run_created")
    _indexes_ensured = True


def reset_agent_tool_call_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


async def create_agent_tool_call(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    user_id: str,
    conversation_id: str,
    tool_name: str,
    input_summary: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    await ensure_agent_tool_call_indexes(database, settings=cfg)
    now = _utc_now()
    document: dict[str, Any] = {
        "runId": ObjectId(run_id) if ObjectId.is_valid(run_id) else run_id,
        "userId": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id,
        "conversationId": ObjectId(conversation_id) if ObjectId.is_valid(conversation_id) else conversation_id,
        "toolName": tool_name,
        "inputSummary": input_summary,
        "status": "running",
        "createdAt": now,
        "updatedAt": now,
    }
    result = await database[cfg.agent_tool_calls_collection].insert_one(document)
    return {
        "id": _format_id(result.inserted_id),
        "toolName": tool_name,
        "status": "running",
    }


async def complete_agent_tool_call(
    database: AsyncIOMotorDatabase,
    *,
    tool_call_id: str,
    status: str = "completed",
    output_summary: str | None = None,
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(tool_call_id):
        return
    cfg = settings or get_settings()
    await database[cfg.agent_tool_calls_collection].update_one(
        {"_id": ObjectId(tool_call_id)},
        {
            "$set": {
                "status": status,
                "outputSummary": output_summary,
                "updatedAt": _utc_now(),
            }
        },
    )
