"""Security tests for academic risk endpoints."""

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def setup_user_with_plan(client, mongo_database, email: str) -> tuple[str, str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(client, email)
    await client.post(
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
    generate_response = await client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]
    analyze_response = await client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )
    analysis_id = analyze_response.json()["data"]["academicRiskAnalysis"]["id"]
    return token, plan_id, analysis_id


@pytest.mark.asyncio
async def test_analyze_requires_jwt(auth_client):
    response = await auth_client.post(
        "/academic-risks/analyze",
        json={"semesterCode": "2025-2", "courseIds": ["665f2b0f2a3f7b2a1a9a7c01"]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_requires_jwt(auth_client):
    response = await auth_client.get("/academic-risks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_analysis_access_returns_404(auth_client, mongo_database):
    _, _, analysis_id_a = await setup_user_with_plan(
        auth_client,
        mongo_database,
        "risk-owner@example.com",
    )

    token_b = await register_access_token(auth_client, "risk-other@example.com")
    response = await auth_client.get(
        f"/academic-risks/{analysis_id_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_plan_analysis_returns_404(auth_client, mongo_database):
    _, plan_id_a, _ = await setup_user_with_plan(
        auth_client,
        mongo_database,
        "risk-plan-owner@example.com",
    )

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token_b = await register_access_token(auth_client, "risk-plan-other@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"planId": plan_id_a},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analyze_rejects_user_id_in_request_body(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "risk-strict@example.com")
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

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "planId": "665f2b0f2a3f7b2a1a9a7fff",
            "userId": "665f2b0f2a3f7b2a1a9a7fff",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_analyze_enforces_ai_rate_limit_with_429(ai_security_client, mongo_database):
    token, plan_id, _ = await setup_user_with_plan(
        ai_security_client,
        mongo_database,
        "risk-rate-limit@example.com",
    )
    second = await ai_security_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )
    assert second.status_code == 429
