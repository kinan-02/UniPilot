"""Stress tests for concurrent student-profile creation."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import get_settings

VALID_PASSWORD = "StrongPass123!"

PROFILE_PAYLOAD = {
    "institutionId": "uni-stress",
    "programType": "BSc",
    "catalogYear": 2025,
    "currentSemesterCode": "2025-1",
}


async def _register(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_profile_creates(auth_client, mongo_database):
    """Parallel profile creates for one user must resolve to a single profile."""
    token = await _register(auth_client, "profile-stress-dup@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    concurrency = 20

    async def create_once():
        return await auth_client.post("/student-profile", headers=headers, json=PROFILE_PAYLOAD)

    start = time.perf_counter()
    responses = await asyncio.gather(*[create_once() for _ in range(concurrency)])
    elapsed_ms = (time.perf_counter() - start) * 1000

    status_codes = [response.status_code for response in responses]
    assert all(code in {201, 409} for code in status_codes), status_codes
    assert status_codes.count(201) >= 1
    assert not any(code >= 500 for code in status_codes)

    settings = get_settings()
    stored = await mongo_database["student_profiles"].count_documents({})
    assert stored == 1

    get_response = await auth_client.get("/student-profile", headers=headers)
    assert get_response.status_code == 200
    assert elapsed_ms < 15000, f"{concurrency} concurrent creates took {elapsed_ms:.1f}ms"
