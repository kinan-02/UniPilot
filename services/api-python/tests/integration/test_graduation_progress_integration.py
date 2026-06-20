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


@pytest.mark.asyncio
async def test_graduation_progress_requires_profile(auth_client):
    token = await register_access_token(auth_client, "grad-no-profile@example.com")
    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graduation_progress_requires_degree(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-no-degree@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "degree must be selected" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_graduation_progress_not_started_without_completed_courses(
    auth_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-not-started@example.com")
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
    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    progress = response.json()["data"]["graduationProgress"]
    assert progress["statusSummary"] == "not_started"
    assert progress["completedCredits"] == 0
    assert progress["totalRequiredCredits"] == 155.0


@pytest.mark.asyncio
async def test_graduation_progress_counts_pool_eligible_ds_elective_only(
    auth_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-pool@example.com")
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

    for course_id, credits in [
        (fixtures["courseBId"], 3.5),
        (fixtures["courseAId"], 4.0),
    ]:
        create = await auth_client.post(
            "/completed-courses",
            headers={"Authorization": f"Bearer {token}"},
            json=build_completed_course_payload(
                course_id,
                creditsEarned=credits,
                semesterCode="2024-1",
                grade=82,
            ),
        )
        assert create.status_code == 201

    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    progress = response.json()["data"]["graduationProgress"]
    assert progress["completedCredits"] == 7.5

    ds_bucket = next(
        item
        for item in progress["requirementProgress"]
        if item["requirementGroupId"].endswith(":elective-ds")
    )
    assert ds_bucket["creditsCompleted"] == 3.5
    assert ds_bucket["eligibilityEnforcement"] == "strict_pool"


@pytest.mark.asyncio
async def test_profile_rejects_unknown_degree_id(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-bad-degree@example.com")
    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": "665f2b0f2a3f7b2a1a9a7fff",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    assert response.status_code == 400
