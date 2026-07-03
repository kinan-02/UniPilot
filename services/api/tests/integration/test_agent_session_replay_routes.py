"""Integration tests for agent session replay route."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_get_agent_session_replay_returns_events(auth_client, mongo_database) -> None:
    token = await register_access_token(auth_client, "mas-replay@example.com")
    user = await mongo_database.users.find_one({"email": "mas-replay@example.com"})
    session_id = str(ObjectId())

    await mongo_database.agent_sessions.insert_one(
        {
            "_id": ObjectId(session_id),
            "userId": user["_id"],
            "type": "next_semester_plan",
            "goal": "Plan next semester",
            "status": "completed",
            "transcript": [],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    fake_events = [
        json.dumps({"event": "goal_analyst", "round": 0}),
        json.dumps({"event": "planner_round_1", "round": 1}),
    ]

    with patch(
        "app.services.agent_session_replay_service.get_redis_client",
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.lrange = AsyncMock(return_value=list(reversed(fake_events)))
        mock_get_client.return_value = mock_client

        response = await auth_client.get(
            f"/agent/sessions/{session_id}/replay",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["replayAvailable"] is True
    assert len(body["data"]["events"]) == 2
    assert body["data"]["events"][0]["event"] == "goal_analyst"
