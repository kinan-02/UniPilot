"""User-owned advisor conversation summaries (no raw message storage)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.semester_plan_repository import parse_object_id


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def ensure_advisor_conversation_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.advisor_conversations_collection]
    await collection.create_index(
        [("userId", 1), ("updatedAt", -1)],
        name="advisor_conversations_user_updated_at",
    )


def build_advisor_conversation_document(
    user_id: str,
    *,
    title: str,
    summary: str,
    exchange_count: int = 1,
    last_confidence: str | None = None,
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for advisor conversation")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "title": title.strip()[:120] or "Advisor chat",
        "summary": summary.strip()[:8000],
        "exchangeCount": max(exchange_count, 1),
        "lastConfidence": last_confidence,
        "createdAt": now,
        "updatedAt": now,
    }


async def create_advisor_conversation(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    title: str,
    summary: str,
    last_confidence: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_advisor_conversation_document(
        user_id,
        title=title,
        summary=summary,
        last_confidence=last_confidence,
    )
    insert_result = await database[settings.advisor_conversations_collection].insert_one(
        document
    )
    return {"_id": insert_result.inserted_id, **document}


async def update_advisor_conversation_summary(
    database: AsyncIOMotorDatabase,
    user_id: str,
    conversation_id: str,
    *,
    title: str,
    summary: str,
    last_confidence: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_conversation_id = parse_object_id(conversation_id)
    if parsed_user_id is None or parsed_conversation_id is None:
        return None

    now = datetime.now(timezone.utc)
    return await database[settings.advisor_conversations_collection].find_one_and_update(
        {"_id": parsed_conversation_id, "userId": parsed_user_id},
        {
            "$set": {
                "title": title.strip()[:120] or "Advisor chat",
                "summary": summary.strip()[:8000],
                "lastConfidence": last_confidence,
                "updatedAt": now,
            },
            "$inc": {"exchangeCount": 1},
        },
        return_document=True,
    )


async def find_advisor_conversation_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    conversation_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_conversation_id = parse_object_id(conversation_id)
    if parsed_user_id is None or parsed_conversation_id is None:
        return None

    return await database[settings.advisor_conversations_collection].find_one(
        {"_id": parsed_conversation_id, "userId": parsed_user_id}
    )


async def list_advisor_conversations_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 30,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return {"conversations": [], "total": 0, "page": 1, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 50)
    skip = (safe_page - 1) * safe_limit
    collection = database[settings.advisor_conversations_collection]
    query = {"userId": parsed_user_id}

    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("updatedAt", -1)
        .skip(skip)
        .limit(safe_limit)
    )
    conversations = [doc async for doc in cursor]
    return {
        "conversations": conversations,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def delete_advisor_conversation_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    conversation_id: str,
    *,
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_conversation_id = parse_object_id(conversation_id)
    if parsed_user_id is None or parsed_conversation_id is None:
        return False

    result = await database[settings.advisor_conversations_collection].delete_one(
        {"_id": parsed_conversation_id, "userId": parsed_user_id}
    )
    return result.deleted_count == 1


def to_public_advisor_conversation(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None

    return {
        "id": str(document["_id"]),
        "title": document.get("title", "Advisor chat"),
        "summary": document.get("summary", ""),
        "exchangeCount": int(document.get("exchangeCount") or 0),
        "lastConfidence": document.get("lastConfidence"),
        "createdAt": _format_datetime(document.get("createdAt")),
        "updatedAt": _format_datetime(document.get("updatedAt")),
    }


def to_public_advisor_conversation_summary(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """List view — same fields; client may truncate summary in UI."""
    return to_public_advisor_conversation(document)
