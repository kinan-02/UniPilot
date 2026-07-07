"""MongoDB persistence for agent conversations."""

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


def _serialize_conversation(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _format_id(document.get("_id")),
        "userId": _format_id(document.get("userId")),
        "title": document.get("title"),
        "status": document.get("status"),
        "entities": document.get("entities") or {},
        "assumptions": document.get("assumptions") or [],
        "lastMessagePreview": document.get("lastMessagePreview"),
        "createdAt": _iso(document.get("createdAt")),
        "updatedAt": _iso(document.get("updatedAt")),
    }


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


async def ensure_agent_conversation_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    cfg = settings or get_settings()
    collection = database[cfg.agent_conversations_collection]
    await collection.create_index(
        [("userId", 1), ("updatedAt", -1)],
        name="agent_conversations_user_updated",
    )
    _indexes_ensured = True


def reset_agent_conversation_indexes_state() -> None:
    global _indexes_ensured
    _indexes_ensured = False


async def create_agent_conversation(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    title: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not ObjectId.is_valid(user_id):
        raise ValueError("Invalid user id for agent conversation")

    cfg = settings or get_settings()
    await ensure_agent_conversation_indexes(database, settings=cfg)
    now = _utc_now()
    document = {
        "userId": ObjectId(user_id),
        "title": (title or "New conversation").strip()[:120],
        "status": "active",
        "entities": {},
        "assumptions": [],
        "lastMessagePreview": None,
        "createdAt": now,
        "updatedAt": now,
    }
    result = await database[cfg.agent_conversations_collection].insert_one(document)
    return _serialize_conversation({"_id": result.inserted_id, **document})


async def find_conversation_by_id_and_user(
    database: AsyncIOMotorDatabase,
    conversation_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return None
    cfg = settings or get_settings()
    document = await database[cfg.agent_conversations_collection].find_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id)}
    )
    return _serialize_conversation(document) if document else None


async def list_conversations_by_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    limit: int = 20,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    if not ObjectId.is_valid(user_id):
        return []
    cfg = settings or get_settings()
    cursor = (
        database[cfg.agent_conversations_collection]
        .find({"userId": ObjectId(user_id)})
        .sort("updatedAt", -1)
        .limit(max(1, min(limit, 50)))
    )
    return [_serialize_conversation(doc) async for doc in cursor]


async def update_conversation_preview(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    preview: str,
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return
    cfg = settings or get_settings()
    await database[cfg.agent_conversations_collection].update_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id)},
        {"$set": {"lastMessagePreview": preview[:200], "updatedAt": _utc_now()}},
    )


async def append_conversation_entities(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    entities: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return
    cfg = settings or get_settings()
    set_fields = {f"entities.{key}": value for key, value in entities.items()}
    set_fields["updatedAt"] = _utc_now()
    await database[cfg.agent_conversations_collection].update_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id)},
        {"$set": set_fields},
    )


async def append_conversation_assumptions(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    assumptions: list[str],
    settings: Settings | None = None,
) -> None:
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return
    if not assumptions:
        return
    cfg = settings or get_settings()
    conversation = await database[cfg.agent_conversations_collection].find_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id)}
    )
    if conversation is None:
        return
    existing = [str(item) for item in (conversation.get("assumptions") or []) if item]
    merged = list(dict.fromkeys([*existing, *[str(item) for item in assumptions if item]]))
    await database[cfg.agent_conversations_collection].update_one(
        {"_id": ObjectId(conversation_id), "userId": ObjectId(user_id)},
        {"$set": {"assumptions": merged, "updatedAt": _utc_now()}},
    )
