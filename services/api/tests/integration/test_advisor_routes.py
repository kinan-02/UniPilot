"""Security and integration tests for advisor routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
async def test_advisor_ask_requires_auth(auth_client):
    response = await auth_client.post("/advisor/ask", json={"question": "מה הסילבוס?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_advisor_ask_validates_question(auth_client, mongo_database):
    token = await register_access_token(auth_client, "advisor-empty@example.com")
    response = await auth_client.post(
        "/advisor/ask",
        json={"question": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_advisor_ask_returns_answer(auth_client, mongo_database):
    token = await register_access_token(auth_client, "advisor-ok@example.com")
    mock_result = {
        "status": "ok",
        "advisor": {
            "question": "מה הסילבוס?",
            "answer": "הסילבוס זמין בקטלוג.",
            "confidence": "high",
            "courseIds": ["00440148"],
            "wikiSlugs": [],
            "sources": [],
            "contacts": [],
            "eligibility": None,
            "semesterResolution": None,
            "retrievalStatus": "ok",
        },
    }

    with patch(
        "app.routes.advisor.ask_advisor_for_user",
        new=AsyncMock(return_value=mock_result),
    ):
        response = await auth_client.post(
            "/advisor/ask",
            json={"question": "מה הסילבוס?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["advisor"]["answer"] == "הסילבוס זמין בקטלוג."


@pytest.mark.asyncio
async def test_advisor_ask_is_503_when_the_agent_is_down(auth_client, mongo_database):
    """End to end through client, service and route: an unreachable agent must
    reach the route's "unavailable" branch, not fall out of it as a 500.

    Patched at the httpx layer on purpose -- patching the service would skip the
    conversion being tested here.
    """
    token = await register_access_token(auth_client, "advisor-down@example.com")

    dead_client = AsyncMock()
    dead_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    dead_client.__aenter__ = AsyncMock(return_value=dead_client)
    dead_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.clients.ai_advisor_client.httpx.AsyncClient",
        return_value=dead_client,
    ):
        response = await auth_client.post(
            "/advisor/ask",
            json={"question": "מה הסילבוס?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_advisor_stream_ends_with_an_error_event_when_the_agent_is_down(
    auth_client, mongo_database
):
    """The stream has already answered 200 by the time the agent is called, so a
    failure has to arrive as an event. A truncated stream leaves the UI waiting
    on a reply that is never coming."""
    token = await register_access_token(auth_client, "advisor-stream-down@example.com")

    dead_client = AsyncMock()
    dead_client.stream = MagicMock(side_effect=httpx.ConnectError("connection refused"))
    dead_client.__aenter__ = AsyncMock(return_value=dead_client)
    dead_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.clients.ai_advisor_client.httpx.AsyncClient",
        return_value=dead_client,
    ):
        response = await auth_client.post(
            "/advisor/ask/stream",
            json={"question": "מה הסילבוס?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
