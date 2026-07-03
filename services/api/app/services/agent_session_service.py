"""Agent session orchestration from the public API."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.queue.mas_jobs import enqueue_mas_session
from app.repositories.agent_session_repository import (
    create_agent_session,
    find_agent_session_by_id_and_user,
    list_agent_sessions_by_user,
    to_public_agent_session,
)


async def start_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_type: str,
    goal: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = await create_agent_session(
        database,
        user_id=user_id,
        session_type=session_type,
        goal=goal,
        constraints=constraints,
    )
    session_id = str(document["_id"])
    enqueued = await enqueue_mas_session(session_id)
    public = to_public_agent_session(document)
    if public is None:
        raise RuntimeError("Failed to serialize agent session")
    public["enqueued"] = enqueued
    return public


async def get_agent_session_for_user(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    document = await find_agent_session_by_id_and_user(database, session_id, user_id)
    return to_public_agent_session(document)


async def list_agent_sessions_for_user(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    documents = await list_agent_sessions_by_user(database, user_id, limit=limit)
    return [
        session
        for document in documents
        if (session := to_public_agent_session(document)) is not None
    ]
