"""Integration tests for agent session clarification route."""

from __future__ import annotations

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
async def test_clarify_agent_session_route(auth_client, mongo_database) -> None:
    token = await register_access_token(auth_client, "mas-clarify@example.com")
    user = await mongo_database.users.find_one({"email": "mas-clarify@example.com"})
    session_id = str(ObjectId())

    await mongo_database.agent_sessions.insert_one(
        {
            "_id": ObjectId(session_id),
            "userId": user["_id"],
            "type": "next_semester_plan",
            "goal": "help",
            "status": "awaiting_clarification",
            "finalDecision": {"clarificationQuestion": "Which courses?"},
            "transcript": [],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )

    with patch(
        "app.services.agent_session_clarify_service.enqueue_mas_session",
        new=AsyncMock(return_value=True),
    ):
        response = await auth_client.post(
            f"/agent/sessions/{session_id}/clarify",
            headers={"Authorization": f"Bearer {token}"},
            json={"clarification": "Plan course 00140008"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["session"]["status"] == "pending"
    assert "00140008" in body["data"]["session"]["goal"]
