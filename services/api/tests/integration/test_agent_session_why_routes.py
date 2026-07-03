"""Integration tests for agent session Why? route."""

from __future__ import annotations

import pytest

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_why_agent_session_returns_grounded_answer(auth_client, mongo_database) -> None:
    token = await register_access_token(auth_client, "mas-why@example.com")
    user = await mongo_database.users.find_one({"email": "mas-why@example.com"})
    assert user is not None

    insert = await mongo_database.agent_sessions.insert_one(
        {
            "userId": user["_id"],
            "type": "next_semester_plan",
            "goal": "Plan next semester",
            "status": "completed",
            "transcript": [
                {
                    "agent_role": "arbiter",
                    "action": "commit",
                    "rationale": "Committed variant balanced with utility 0.81.",
                    "references": ["utility:balanced"],
                    "payload": {
                        "course_ids": ["00140008"],
                        "reasoningTrace": {
                            "kind": "arbitration",
                            "chosen_variant": "balanced",
                            "utility": 0.81,
                        },
                    },
                }
            ],
            "finalDecision": {
                "course_ids": ["00140008"],
                "utilityBreakdown": {"utility": 0.81},
                "arbitration": {"chosen_variant": "balanced", "considered_variants": ["balanced"]},
            },
            "rounds": 1,
        }
    )

    response = await auth_client.post(
        f"/agent/sessions/{insert.inserted_id}/why",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Why was this variant chosen?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "arbiter" in body["data"]["answer"]
    assert body["data"]["citations"]
    assert body["data"]["source"] == "deterministic_transcript"
