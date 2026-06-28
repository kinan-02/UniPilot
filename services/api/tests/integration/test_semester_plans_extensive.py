"""Extensive integration tests for semester plans API."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_and_profile(client, email: str, degree_id: str, **preferences) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    token = response.json()["data"]["accessToken"]

    profile_payload = {
        "institutionId": "technion",
        "programType": "BSc",
        "degreeId": degree_id,
        "catalogYear": 2025,
        "currentSemesterCode": "2025-1",
    }
    if preferences:
        profile_payload["preferences"] = preferences

    profile_response = await client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json=profile_payload,
    )
    assert profile_response.status_code in {200, 201}
    return token


@pytest.mark.asyncio
async def test_generate_uses_semester_matrix_mandatory_courses(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-mandatory@example.com", fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 8},
    )

    assert response.status_code == 201
    plan = response.json()["data"]["semesterPlan"]
    assert plan["assumptions"]["mandatorySource"] == "semester_matrix"
    numbers = [course["courseNumber"] for course in plan["semesters"][0]["plannedCourses"]]
    assert fixtures["courseANumber"] in numbers
    assert fixtures["courseDNumber"] in numbers
    assert numbers.index(fixtures["courseANumber"]) < numbers.index(fixtures["courseDNumber"])


@pytest.mark.asyncio
async def test_generate_after_completing_semester_one_moves_to_semester_two(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-progress@example.com", fixtures["programId"])

    for course_id, credits in [
        (fixtures["courseAId"], 4.0),
        (fixtures["courseDId"], 3.5),
    ]:
        create_response = await auth_client.post(
            "/completed-courses",
            headers={"Authorization": f"Bearer {token}"},
            json=build_completed_course_payload(course_id, grade=80, creditsEarned=credits),
        )
        assert create_response.status_code == 201

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )

    assert response.status_code == 201
    numbers = [
        course["courseNumber"]
        for course in response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"]
    ]
    assert fixtures["courseANumber"] not in numbers
    assert fixtures["courseDNumber"] not in numbers
    assert fixtures["courseENumber"] in numbers


@pytest.mark.asyncio
async def test_generate_rejects_invalid_semester_code(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-invalid-sem@example.com", fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-4", "maxCredits": 6},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_accepts_summer_semester_code(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-summer-sem@example.com", fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-3", "maxCredits": 6},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_generate_rejects_invalid_credit_increments(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-invalid-credits@example.com", fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 3.25},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_rejects_min_credits_above_max(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-min-max@example.com", fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 6, "minCredits": 9},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_pagination_limits(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-pagination@example.com", fixtures["programId"])

    for index in range(3):
        await auth_client.post(
            "/semester-plans/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"semesterCode": "2025-2", "name": f"Plan {index}", "maxCredits": 6},
        )

    response = await auth_client.get(
        "/semester-plans?page=1&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["semesterPlans"]) == 2
    assert data["pagination"]["total"] >= 3


@pytest.mark.asyncio
async def test_get_plan_rejects_invalid_object_id(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-bad-id@example.com", fixtures["programId"])

    response = await auth_client.get(
        "/semester-plans/not-a-valid-object-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_with_profile_preference_default(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(
        auth_client,
        "matrix-pref-default@example.com",
        fixtures["programId"],
        maxCreditsPerSemester=7,
    )

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["semesterPlan"]["explanation"]["maxCredits"] == 7


@pytest.mark.asyncio
async def test_generate_multiple_plans_are_independent(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_and_profile(auth_client, "matrix-multi@example.com", fixtures["programId"])

    first = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 4, "name": "Tight plan"},
    )
    second = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12, "name": "Wide plan"},
    )

    first_credits = first.json()["data"]["semesterPlan"]["explanation"]["totalRecommendedCredits"]
    second_credits = second.json()["data"]["semesterPlan"]["explanation"]["totalRecommendedCredits"]
    assert second_credits >= first_credits
