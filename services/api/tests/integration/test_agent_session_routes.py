"""Integration tests for MAS agent session routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
async def test_agent_sessions_require_auth(auth_client):
    response = await auth_client.post(
        "/agent/sessions",
        json={"goal": "Plan my next semester"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_agent_session_returns_202(auth_client, mongo_database):
    token = await register_access_token(auth_client, "mas-session@example.com")

    with patch(
        "app.services.agent_session_service.enqueue_mas_session",
        new=AsyncMock(return_value=True),
    ):
        response = await auth_client.post(
            "/agent/sessions",
            json={"goal": "Plan courses 00940139 for next semester"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["data"]["session"]["status"] == "pending"
    assert body["data"]["session"]["goal"].startswith("Plan courses")


@pytest.mark.asyncio
async def test_get_agent_session_enforces_ownership(auth_client, mongo_database):
    token_a = await register_access_token(auth_client, "mas-owner@example.com")
    token_b = await register_access_token(auth_client, "mas-other@example.com")

    with patch(
        "app.services.agent_session_service.enqueue_mas_session",
        new=AsyncMock(return_value=True),
    ):
        create_response = await auth_client.post(
            "/agent/sessions",
            json={"goal": "Plan next semester"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    session_id = create_response.json()["data"]["session"]["id"]

    own_response = await auth_client.get(
        f"/agent/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert own_response.status_code == 200

    other_response = await auth_client.get(
        f"/agent/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert other_response.status_code == 404
