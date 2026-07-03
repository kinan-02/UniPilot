"""Unit tests for agent session persistence helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from app.sessions.processor import (
    complete_session,
    ensure_agent_session_indexes,
    find_session_by_id,
)


@pytest.mark.asyncio
async def test_find_session_by_id_rejects_invalid_object_id() -> None:
    result = await find_session_by_id(MagicMock(), "not-valid")
    assert result is None


@pytest.mark.asyncio
async def test_ensure_agent_session_indexes_creates_indexes(monkeypatch) -> None:
    database = MagicMock()
    collection = MagicMock()
    collection.create_index = AsyncMock()
    database.__getitem__ = MagicMock(return_value=collection)

    class _Settings:
        agent_sessions_collection = "agent_sessions"

    monkeypatch.setattr("app.sessions.processor.get_settings", lambda: _Settings())

    await ensure_agent_session_indexes(database)

    assert collection.create_index.await_count == 2


@pytest.mark.asyncio
async def test_complete_session_updates_document(monkeypatch) -> None:
    database = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    database.__getitem__ = MagicMock(return_value=collection)

    class _Settings:
        agent_sessions_collection = "agent_sessions"

    monkeypatch.setattr("app.sessions.processor.get_settings", lambda: _Settings())

    session_id = str(ObjectId())
    await complete_session(
        database,
        session_id,
        status="completed",
        transcript=[{"agent_role": "arbiter"}],
        final_decision={"course_ids": ["00140008"]},
        utility_breakdown={"total": 0.8},
        rounds=2,
    )

    collection.update_one.assert_awaited_once()
    update_doc = collection.update_one.await_args.args[1]["$set"]
    assert update_doc["status"] == "completed"
    assert update_doc["rounds"] == 2
