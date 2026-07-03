"""Integration tests for UniPilot Agent conversation routes."""

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
async def test_agent_conversations_require_auth(auth_client):
    response = await auth_client.post("/agent/conversations", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_conversations(auth_client):
    token = await register_access_token(auth_client, "agent-conv@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post(
        "/agent/conversations",
        json={"title": "Graduation check"},
        headers=headers,
    )
    assert create_response.status_code == 200
    conversation = create_response.json()["data"]["conversation"]
    assert conversation["title"] == "Graduation check"
    assert conversation["status"] == "active"

    list_response = await auth_client.get("/agent/conversations", headers=headers)
    assert list_response.status_code == 200
    conversations = list_response.json()["data"]["conversations"]
    assert any(item["id"] == conversation["id"] for item in conversations)


@pytest.mark.asyncio
async def test_send_message_json_mode_without_profile(auth_client):
    token = await register_access_token(auth_client, "agent-msg@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post("/agent/conversations", json={}, headers=headers)
    conversation_id = create_response.json()["data"]["conversation"]["id"]

    message_response = await auth_client.post(
        f"/agent/conversations/{conversation_id}/messages",
        json={"content": "What am I missing to graduate?"},
        headers=headers,
    )
    assert message_response.status_code == 200
    body = message_response.json()["data"]
    assert "student profile" in body["text"].lower()
    assert body["messageId"]
    assert any(event.get("type") == "agent.step.started" for event in body["events"])
