"""MongoDB persistence for agent messages."""

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


def _serialize_message(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _format_id(document.get("_id")),
        "conversationId": _format_id(document.get("conversationId")),
        "userId": _format_id(document.get("userId")),
        "role": document.get("role"),
        "content": document.get("content"),
        "structuredBlocks": document.get("structuredBlocks") or [],
        "attachments": document.get("attachments") or [],
        "warnings": document.get("warnings") or [],
        "suggestedPrompts": document.get("suggestedPrompts") or [],
        "proposedActions": document.get("proposedActions") or [],
        "assumptions": document.get("assumptions") or [],
        "usedSources": document.get("usedSources") or [],
        "runId": _format_id(document.get("runId")) if document.get("runId") else None,
        "createdAt": _iso(document.get("createdAt")),
    }


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


async def ensure_agent_message_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_messages_collection]
    await collection.create_index(
        [("conversationId", 1), ("createdAt", 1)],
        name="agent_messages_conversation_created",
    )
    _indexes_ensured = True


def reset_agent_message_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


async def create_agent_message(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    structured_blocks: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    warnings: list[str] | None = None,
    suggested_prompts: list[str] | None = None,
    proposed_actions: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
    used_sources: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        raise ValueError("Invalid ids for agent message")

    cfg = settings or get_settings()
    await ensure_agent_message_indexes(database, settings=cfg)
    now = _utc_now()
    document: dict[str, Any] = {
        "conversationId": ObjectId(conversation_id),
        "userId": ObjectId(user_id),
        "role": role,
        "content": content,
        "structuredBlocks": structured_blocks or [],
        "attachments": attachments or [],
        "warnings": warnings or [],
        "suggestedPrompts": suggested_prompts or [],
        "proposedActions": proposed_actions or [],
        "assumptions": assumptions or [],
        "usedSources": used_sources or [],
        "createdAt": now,
    }
    if run_id and ObjectId.is_valid(run_id):
        document["runId"] = ObjectId(run_id)

    result = await database[cfg.agent_messages_collection].insert_one(document)
    return _serialize_message({"_id": result.inserted_id, **document})


async def list_messages_for_conversation(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    limit: int = 100,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return []
    cfg = settings or get_settings()
    cursor = (
        database[cfg.agent_messages_collection]
        .find(
            {
                "conversationId": ObjectId(conversation_id),
                "userId": ObjectId(user_id),
            }
        )
        .sort("createdAt", 1)
        .limit(max(1, min(limit, 200)))
    )
    return [_serialize_message(doc) async for doc in cursor]
