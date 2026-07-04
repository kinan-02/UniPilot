"""Integration tests for simulation routes (AGT-3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    insert_official_completed_course_for_tests,
)
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def seed_profile_with_completed_course(client, token: str, mongo_database) -> dict:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    profile_response = await client.post(
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
    assert profile_response.status_code == 201
    user_id = profile_response.json()["data"]["profile"]["userId"]
    await insert_official_completed_course_for_tests(
        mongo_database,
        user_id,
        build_completed_course_payload(
            fixtures["courseEId"],
            semesterCode="2024-1",
            grade=85,
            creditsEarned=3.5,
        ),
    )
    return fixtures


@pytest.mark.asyncio
async def test_simulation_scenarios_require_auth(auth_client):
    response = await auth_client.post(
        "/simulations/scenarios",
        json={
            "name": "Drop DS",
            "operations": [{"type": "drop_course", "courseNumber": "00940219"}],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_and_run_drop_course_simulation(auth_client, mongo_database):
    token = await register_access_token(auth_client, "sim-drop@example.com")
    fixtures = await seed_profile_with_completed_course(auth_client, token, mongo_database)

    create_response = await auth_client.post(
        "/simulations/scenarios",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Drop data structures",
            "semesterCode": "2025-1",
            "operations": [{"type": "drop_course", "courseNumber": fixtures["courseENumber"]}],
        },
    )
    assert create_response.status_code == 201
    scenario_id = create_response.json()["data"]["simulationScenario"]["id"]

    with patch(
        "app.clients.ai_simulation_client.narrate_simulation_impact",
        new=AsyncMock(return_value=None),
    ):
        run_response = await auth_client.post(
            f"/simulations/scenarios/{scenario_id}/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"executionMode": "sync"},
        )

    assert run_response.status_code == 200
    body = run_response.json()["data"]
    assert body["asyncAccepted"] is False
    result = body["simulationResult"]
    assert result["summary"]
    assert result["beforeSnapshot"]["graduation"]["completedCredits"] > 0
    assert result["afterSnapshot"]["graduation"]["completedCredits"] == 0
    assert result["deltas"]["progress"]["completedCreditsDelta"] < 0


@pytest.mark.asyncio
async def test_create_simulation_from_text(auth_client, mongo_database):
    token = await register_access_token(auth_client, "sim-text@example.com")
    await seed_profile_with_completed_course(auth_client, token, mongo_database)

    response = await auth_client.post(
        "/simulations/scenarios/from-text",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "Drop course 00940219 from my transcript"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["parsedOperations"][0]["type"] == "drop_course"


@pytest.mark.asyncio
async def test_run_simulation_auto_offloads_heavy_scenario(auth_client, mongo_database):
    token = await register_access_token(auth_client, "sim-async@example.com")
    await seed_profile_with_completed_course(auth_client, token, mongo_database)

    create_response = await auth_client.post(
        "/simulations/scenarios",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Heavy scenario",
            "semesterCode": "2025-1",
            "operations": [
                {"type": "drop_course", "courseNumber": "00940219"},
                {"type": "add_planned_course", "courseNumber": "00940411"},
                {"type": "add_planned_course", "courseNumber": "00940345"},
            ],
        },
    )
    scenario_id = create_response.json()["data"]["simulationScenario"]["id"]

    with patch(
        "app.services.ai_job_service.create_job_for_user",
        new=AsyncMock(return_value={"status": "queued", "job": {"id": "665f1c2e3d4a5b6c7d8e9f01", "status": "pending"}}),
    ):
        run_response = await auth_client.post(
            f"/simulations/scenarios/{scenario_id}/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"executionMode": "auto"},
        )

    assert run_response.status_code == 202
    assert run_response.json()["data"]["asyncAccepted"] is True
