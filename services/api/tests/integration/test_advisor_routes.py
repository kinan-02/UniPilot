"""Security and integration tests for advisor routes."""

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
        "conversation": {
            "id": "665f1c2e3d4a5b6c7d8e9f01",
            "title": "סילבוס",
            "summary": "הסטודנט שאל על סילבוס; היועץ הפנה לקטלוג.",
            "exchangeCount": 1,
            "lastConfidence": "high",
            "createdAt": "2026-06-28T12:00:00Z",
            "updatedAt": "2026-06-28T12:00:00Z",
        },
    }

    with patch(
        "app.routes.advisor.ask_advisor_or_enqueue",
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
    assert body["data"]["asyncAccepted"] is False
    assert body["data"]["conversation"]["summary"]


@pytest.mark.asyncio
async def test_advisor_ask_auto_offloads_heavy_question(auth_client, mongo_database):
    token = await register_access_token(auth_client, "advisor-async@example.com")
    mock_queued = {
        "status": "queued",
        "offloadReason": "planning_intent",
        "job": {
            "id": "665f1c2e3d4a5b6c7d8e9f02",
            "type": "advisor_deep_plan",
            "status": "pending",
            "payload": {"question": "What should I take next semester?"},
        },
    }

    with patch(
        "app.routes.advisor.ask_advisor_or_enqueue",
        new=AsyncMock(return_value=mock_queued),
    ):
        response = await auth_client.post(
            "/advisor/ask",
            json={"question": "What should I take next semester?"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["data"]["asyncAccepted"] is True
    assert body["data"]["offloadReason"] == "planning_intent"
    assert body["data"]["job"]["status"] == "pending"


@pytest.mark.asyncio
async def test_advisor_ask_force_sync_skips_auto_offload(auth_client, mongo_database):
    token = await register_access_token(auth_client, "advisor-sync@example.com")

    with patch(
        "app.routes.advisor.ask_advisor_or_enqueue",
        new=AsyncMock(
            return_value={
                "status": "ok",
                "advisor": {
                    "question": "What should I take next semester?",
                    "answer": "Instant reply",
                    "confidence": "medium",
                    "courseIds": [],
                    "wikiSlugs": [],
                    "sources": [],
                    "contacts": [],
                },
            }
        ),
    ) as orchestrator_mock:
        response = await auth_client.post(
            "/advisor/ask",
            json={
                "question": "What should I take next semester?",
                "execution_mode": "sync",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert orchestrator_mock.await_args.kwargs["execution_mode"] == "sync"


@pytest.mark.asyncio
async def test_advisor_conversations_requires_auth(auth_client):
    response = await auth_client.get("/advisor/conversations")
    assert response.status_code == 401
