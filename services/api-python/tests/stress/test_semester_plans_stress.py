"""Stress tests for semester plan generation."""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def _register(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_concurrent_generate_requests_for_same_user(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await _register(auth_client, "semester-stress-user@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )

    async def generate(index: int):
        return await auth_client.post(
            "/semester-plans/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"semesterCode": "2025-2", "maxCredits": 9, "name": f"Stress {index}"},
        )

    start = time.perf_counter()
    responses = await asyncio.gather(*[generate(index) for index in range(20)])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert all(response.status_code == 201 for response in responses)
    assert elapsed_ms < 15000, f"20 concurrent generates took {elapsed_ms:.1f}ms"

    list_response = await auth_client.get(
        "/semester-plans?limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.json()["data"]["pagination"]["total"] >= 20


@pytest.mark.asyncio
async def test_many_users_generate_plans_in_parallel(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)

    async def user_flow(index: int):
        token = await _register(auth_client, f"semester-stress-{index}@example.com")
        await auth_client.post(
            "/student-profile",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "institutionId": "technion",
                "programType": "BSc",
                "degreeId": fixtures["programId"],
                "catalogYear": 2025,
                "currentSemesterCode": "2025-1",
            },
        )
        return await auth_client.post(
            "/semester-plans/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"semesterCode": "2025-2", "maxCredits": 6},
        )

    start = time.perf_counter()
    responses = await asyncio.gather(*[user_flow(index) for index in range(15)])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert all(response.status_code == 201 for response in responses)
    assert elapsed_ms < 20000, f"15 user generates took {elapsed_ms:.1f}ms"
