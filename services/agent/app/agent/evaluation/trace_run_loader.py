"""Fetch agent run metadata for eval tracing."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.agent_conversation_repository import find_conversation_by_id_and_user


async def get_latest_agent_run_for_conversation(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    cfg = settings or get_settings()
    if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
        return None
    document = await database[cfg.agent_runs_collection].find_one(
        {
            "conversationId": ObjectId(conversation_id),
            "userId": ObjectId(user_id),
        },
        sort=[("startedAt", -1)],
    )
    return document


async def load_turn_trace_context(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    settings: Settings | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (retrieval_metadata, conversation_entities) for the latest run."""
    run = await get_latest_agent_run_for_conversation(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        settings=settings,
    )
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    entities = dict((conversation or {}).get("entities") or {})
    if run is None:
        return None, entities
    metadata = dict(run.get("retrievalMetadata") or {})
    metadata.setdefault("intent", run.get("intent"))
    metadata.setdefault("retrievalProfile", run.get("retrievalProfile"))
    return metadata, entities
