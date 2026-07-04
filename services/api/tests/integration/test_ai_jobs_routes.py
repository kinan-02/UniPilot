"""Integration and security tests for async AI jobs."""

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
async def test_create_ai_job_requires_auth(auth_client):
    response = await auth_client.post(
        "/ai/jobs",
        json={
            "type": "advisor_deep_plan",
            "payload": {"question": "What is the syllabus for 00440148?"},
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_ai_job_validates_payload(auth_client, mongo_database):
    token = await register_access_token(auth_client, "ai-job-invalid@example.com")
    response = await auth_client.post(
        "/ai/jobs",
        json={"type": "advisor_deep_plan", "payload": {"question": ""}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_and_process_ai_job_flow(auth_client, mongo_database, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    from app.config import get_settings

    get_settings.cache_clear()

    token = await register_access_token(auth_client, "ai-job-flow@example.com")
    advisor_result = {
        "status": "ok",
        "advisor": {
            "question": "What is the syllabus?",
            "answer": "Syllabus details here.",
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
        "app.services.ai_job_handlers.ask_advisor_for_user",
        new=AsyncMock(return_value=advisor_result),
    ):
        create_response = await auth_client.post(
            "/ai/jobs",
            json={
                "type": "advisor_deep_plan",
                "payload": {"question": "What is the syllabus for 00440148?"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert create_response.status_code == 202
        job_id = create_response.json()["data"]["job"]["id"]
        assert create_response.json()["data"]["job"]["status"] == "pending"

        process_response = await auth_client.post(
            f"/internal/ai-jobs/{job_id}/process",
            headers={"X-Internal-Service-Token": "test-internal-token"},
        )
        assert process_response.status_code == 200
        assert process_response.json()["data"]["status"] == "completed"

    get_response = await auth_client.get(
        f"/ai/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_response.status_code == 200
    job = get_response.json()["data"]["job"]
    assert job["status"] == "completed"
    assert job["result"]["advisor"]["answer"] == "Syllabus details here."


@pytest.mark.asyncio
async def test_get_ai_job_enforces_ownership(auth_client, mongo_database, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    from app.config import get_settings

    get_settings.cache_clear()

    owner_token = await register_access_token(auth_client, "ai-job-owner@example.com")
    other_token = await register_access_token(auth_client, "ai-job-other@example.com")

    with patch(
        "app.services.ai_job_handlers.ask_advisor_for_user",
        new=AsyncMock(
            return_value={
                "status": "ok",
                "advisor": {"answer": "ok", "confidence": "medium"},
            }
        ),
    ):
        create_response = await auth_client.post(
            "/ai/jobs",
            json={
                "type": "advisor_deep_plan",
                "payload": {"question": "Hello"},
            },
            headers={"Authorization": f"Bearer {owner_token}"},
        )

    job_id = create_response.json()["data"]["job"]["id"]

    other_response = await auth_client.get(
        f"/ai/jobs/{job_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_response.status_code == 404


@pytest.mark.asyncio
async def test_internal_process_requires_token(auth_client, mongo_database, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    from app.config import get_settings

    get_settings.cache_clear()

    token = await register_access_token(auth_client, "ai-job-internal@example.com")
    create_response = await auth_client.post(
        "/ai/jobs",
        json={
            "type": "advisor_deep_plan",
            "payload": {"question": "Need token"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_response.json()["data"]["job"]["id"]

    response = await auth_client.post(f"/internal/ai-jobs/{job_id}/process")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_ai_job_rate_limited(ai_security_client, mongo_database):
    token = await register_access_token(ai_security_client, "ai-job-rate@example.com")
    body = {
        "type": "advisor_deep_plan",
        "payload": {"question": "First"},
    }

    first = await ai_security_client.post(
        "/ai/jobs",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await ai_security_client.post(
        "/ai/jobs",
        json={"type": "advisor_deep_plan", "payload": {"question": "Second"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 202
    assert second.status_code == 429
