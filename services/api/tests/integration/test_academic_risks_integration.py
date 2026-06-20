"""Integration tests for academic risk endpoints."""

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def create_profile(client, token: str, *, degree_id: str | None = None) -> None:
    payload = {
        "institutionId": "technion",
        "programType": "BSc",
        "catalogYear": 2025,
        "currentSemesterCode": "2025-1",
        "preferences": {"maxCreditsPerSemester": 12},
    }
    if degree_id is not None:
        payload["degreeId"] = degree_id
    response = await client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code in {200, 201}


@pytest.mark.asyncio
async def test_analyze_persisted_semester_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-plan@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )

    assert response.status_code == 201
    analysis = response.json()["data"]["academicRiskAnalysis"]
    assert analysis["analyzerType"] == "deterministic"
    assert analysis["planId"] == plan_id
    assert "totalRisks" in analysis["summary"]
    assert all(risk["source"] == "rule" for risk in analysis["risks"])


@pytest.mark.asyncio
async def test_analyze_adhoc_proposed_courses(auth_client, mongo_database):
    from bson import ObjectId

    from app.config import get_settings

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    settings = get_settings()
    await mongo_database[settings.courses_collection].update_one(
        {"_id": ObjectId(fixtures["courseEId"])},
        {"$set": {"prerequisites": [ObjectId(fixtures["courseDId"])]}},
    )

    token = await register_access_token(auth_client, "academic-risk-adhoc@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "courseIds": [fixtures["courseEId"]],
            "maxCredits": 6,
        },
    )

    assert response.status_code == 201
    analysis = response.json()["data"]["academicRiskAnalysis"]
    assert analysis["analysisSource"] == "adhoc_courses"
    assert any(risk["riskType"] == "unmet_prerequisites" for risk in analysis["risks"])


@pytest.mark.asyncio
async def test_list_academic_risk_history(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-list@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]

    await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )
    await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "courseIds": [fixtures["courseDId"]],
        },
    )

    response = await auth_client.get(
        "/academic-risks",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["academicRiskAnalyses"]) >= 2
    assert data["pagination"]["total"] >= 2


@pytest.mark.asyncio
async def test_get_academic_risk_analysis_by_id(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-get@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]

    analyze_response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": plan_id},
    )
    analysis_id = analyze_response.json()["data"]["academicRiskAnalysis"]["id"]

    response = await auth_client.get(
        f"/academic-risks/{analysis_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["academicRiskAnalysis"]["id"] == analysis_id
    assert response.json()["data"]["academicRiskAnalysis"]["risks"] is not None


@pytest.mark.asyncio
async def test_detects_completed_course_in_adhoc_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-completed@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json=build_completed_course_payload(
            fixtures["courseDId"],
            grade=90,
            creditsEarned=3.5,
        ),
    )

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "courseIds": [fixtures["courseDId"]],
        },
    )

    assert response.status_code == 201
    assert any(
        risk["riskType"] == "course_already_completed"
        for risk in response.json()["data"]["academicRiskAnalysis"]["risks"]
    )


@pytest.mark.asyncio
async def test_analyze_returns_404_when_profile_missing(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-no-profile@example.com")

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": "665f2b0f2a3f7b2a1a9a7fff"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analyze_returns_400_when_degree_not_selected(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-no-degree@example.com")
    await create_profile(auth_client, token, degree_id=None)

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": "665f2b0f2a3f7b2a1a9a7fff"},
    )

    assert response.status_code == 400
    assert "degree must be selected" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_analyze_returns_404_for_invalid_plan_id(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "academic-risk-bad-plan@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/academic-risks/analyze",
        headers={"Authorization": f"Bearer {token}"},
        json={"planId": "665f2b0f2a3f7b2a1a9a7fff"},
    )

    assert response.status_code == 404
