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
