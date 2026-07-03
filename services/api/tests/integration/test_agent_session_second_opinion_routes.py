"""Integration tests for agent session second-opinion route."""

from __future__ import annotations

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
async def test_second_opinion_starts_new_session_with_profile(auth_client, mongo_database) -> None:
    token = await register_access_token(auth_client, "mas-second@example.com")
    user = await mongo_database.users.find_one({"email": "mas-second@example.com"})
    assert user is not None

    insert = await mongo_database.agent_sessions.insert_one(
        {
            "userId": user["_id"],
            "type": "next_semester_plan",
            "goal": "Plan next semester",
            "status": "completed",
            "constraints": {"maxCredits": 20},
            "transcript": [],
            "finalDecision": {"course_ids": ["00140008"]},
            "rounds": 1,
        }
    )

    response = await auth_client.post(
        f"/agent/sessions/{insert.inserted_id}/second-opinion",
        headers={"Authorization": f"Bearer {token}"},
        json={"utility_profile": "risk_averse"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["data"]["utilityProfile"] == "risk_averse"
    assert body["data"]["sourceSessionId"] == str(insert.inserted_id)
    assert body["data"]["session"]["status"] in {"queued", "running", "pending"}

    created = await mongo_database.agent_sessions.find_one(
        {"_id": ObjectId(body["data"]["session"]["id"])}
    )
    assert created is not None
    assert created["constraints"]["utilityProfile"] == "risk_averse"
    assert created["constraints"]["secondOpinionOf"] == str(insert.inserted_id)


@pytest.mark.asyncio
async def test_second_opinion_rejects_incomplete_session(auth_client, mongo_database) -> None:
    token = await register_access_token(auth_client, "mas-second-fail@example.com")
    user = await mongo_database.users.find_one({"email": "mas-second-fail@example.com"})
    assert user is not None

    insert = await mongo_database.agent_sessions.insert_one(
        {
            "userId": user["_id"],
            "type": "next_semester_plan",
            "goal": "Plan next semester",
            "status": "running",
            "transcript": [],
            "rounds": 0,
        }
    )

    response = await auth_client.post(
        f"/agent/sessions/{insert.inserted_id}/second-opinion",
        headers={"Authorization": f"Bearer {token}"},
        json={"utility_profile": "aggressive"},
    )
    assert response.status_code == 400
