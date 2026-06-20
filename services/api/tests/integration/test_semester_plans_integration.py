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
async def test_generate_semester_plan_creates_deterministic_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-generate@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 9},
    )

    assert response.status_code == 201
    body = response.json()
    plan = body["data"]["semesterPlan"]
    assert plan["plannerType"] == "deterministic"
    assert len(plan["explanation"]["rulesApplied"]) > 0
    assert len(plan["semesters"][0]["plannedCourses"]) > 0
    assert plan["semesters"][0]["plannedCourses"][0]["courseId"]


@pytest.mark.asyncio
async def test_list_semester_plans_returns_history(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-list@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 6},
    )

    response = await auth_client.get(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["semesterPlans"]) >= 1
    assert data["pagination"]["total"] >= 1


@pytest.mark.asyncio
async def test_get_semester_plan_by_id(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-get@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 6},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]

    response = await auth_client.get(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["semesterPlan"]["id"] == plan_id
    assert response.json()["data"]["semesterPlan"]["explanation"]


@pytest.mark.asyncio
async def test_completed_courses_are_not_recommended_again(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-completed@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json=build_completed_course_payload(
            fixtures["courseBId"],
            grade=80,
            creditsEarned=3.5,
        ),
    )

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )

    recommended_ids = [
        course["courseId"]
        for course in response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"]
    ]
    assert fixtures["courseBId"] not in recommended_ids


@pytest.mark.asyncio
async def test_generate_returns_404_without_profile(auth_client):
    token = await register_access_token(auth_client, "semester-no-profile@example.com")
    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_returns_400_without_degree(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-no-degree@example.com")
    await create_profile(auth_client, token)

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )
    assert response.status_code == 400
    assert "degree must be selected" in response.json()["error"].lower()
