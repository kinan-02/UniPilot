"""Stress tests for concurrent completed-course creation."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import get_settings
from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)

VALID_PASSWORD = "StrongPass123!"


async def _register(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_completed_course_creates(auth_client, mongo_database):
    """Many parallel creates with identical course+attempt must not 5xx and leave one record."""
    catalog = await seed_production_course_fixture(mongo_database)
    token = await _register(auth_client, "completed-stress-dup@example.com")
    payload = build_completed_course_payload(catalog["courseId"])
    headers = {"Authorization": f"Bearer {token}"}
    concurrency = 25

    async def create_once():
        return await auth_client.post("/completed-courses", headers=headers, json=payload)

    start = time.perf_counter()
    responses = await asyncio.gather(*[create_once() for _ in range(concurrency)])
    elapsed_ms = (time.perf_counter() - start) * 1000

    status_codes = [response.status_code for response in responses]
    assert all(code in {201, 409} for code in status_codes), status_codes
    assert status_codes.count(201) >= 1
    assert not any(code >= 500 for code in status_codes)

    settings = get_settings()
    stored = await mongo_database[settings.completed_courses_collection].count_documents({})
    assert stored == 1

    list_response = await auth_client.get("/completed-courses", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["data"]["pagination"]["total"] == 1
    assert elapsed_ms < 15000, f"{concurrency} concurrent creates took {elapsed_ms:.1f}ms"
