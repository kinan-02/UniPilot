"""Unit tests for agent session clarification resume."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.agent_session_clarify_service import (
    _merge_goal_with_clarification,
    clarify_agent_session,
)


def test_merge_goal_with_clarification() -> None:
    merged = _merge_goal_with_clarification(goal="help", clarification="Plan course 00140008")
    assert "help" in merged
    assert "00140008" in merged


@pytest.mark.asyncio
async def test_clarify_agent_session_rejects_non_clarification_state(mongo_database) -> None:
    user_id = str(ObjectId())
    session_id = str(ObjectId())
    await mongo_database.agent_sessions.insert_one(
        {
            "_id": ObjectId(session_id),
            "userId": ObjectId(user_id),
            "type": "next_semester_plan",
            "goal": "help",
            "status": "completed",
            "transcript": [],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    result = await clarify_agent_session(
        mongo_database,
        user_id=user_id,
        session_id=session_id,
        clarification="Plan course 00140008",
    )
    assert result["status"] == "invalid_state"


@pytest.mark.asyncio
async def test_clarify_agent_session_resumes_pending(mongo_database) -> None:
    user_id = str(ObjectId())
    session_id = str(ObjectId())
    await mongo_database.agent_sessions.insert_one(
        {
            "_id": ObjectId(session_id),
            "userId": ObjectId(user_id),
            "type": "next_semester_plan",
            "goal": "help",
            "status": "awaiting_clarification",
            "finalDecision": {"clarificationQuestion": "Which courses?"},
            "transcript": [{"agent_role": "goal_analyst", "action": "critique"}],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    with patch(
        "app.services.agent_session_clarify_service.enqueue_existing_agent_session",
        new=AsyncMock(return_value=True),
    ):
        result = await clarify_agent_session(
            mongo_database,
            user_id=user_id,
            session_id=session_id,
            clarification="Plan course 00140008 with a light load",
        )

    assert result["status"] == "ok"
    assert result["session"]["status"] == "pending"
    assert "00140008" in result["session"]["goal"]

    stored = await mongo_database.agent_sessions.find_one({"_id": ObjectId(session_id)})
    assert stored is not None
    assert stored["status"] == "pending"
    assert len(stored.get("priorTranscript") or []) == 1
    assert len(stored.get("clarifications") or []) == 1
