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


@pytest.mark.asyncio
async def test_semester_plans_require_jwt(auth_client):
    response = await auth_client.post("/semester-plans/generate", json={"semesterCode": "2025-2"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_suggest_courses_requires_jwt(auth_client):
    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        json={"semesterCode": "2025-2", "maxCredits": 9},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_suggest_schedule_requires_jwt(auth_client):
    response = await auth_client.post(
        "/semester-plans/suggest-schedule",
        json={
            "semesterCode": "2025-2",
            "plannedCourses": [
                {
                    "courseId": "665f2b0f2a3f7b2a1a9a7c01",
                    "courseNumber": "00940345",
                }
            ],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_plan_access_returns_404(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)

    owner_token = await register_access_token(auth_client, "semester-owner@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"semesterCode": "2025-2", "maxCredits": 6},
    )
    plan_id = generate_response.json()["data"]["semesterPlan"]["id"]

    other_token = await register_access_token(auth_client, "semester-other@example.com")
    response = await auth_client.get(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_rejects_unknown_fields(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "semester-strict@example.com")
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
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "userId": "evil"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_courses_rejects_unknown_fields(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "suggest-strict@example.com")
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
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "plannedCourses": []},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_schedule_rejects_unknown_fields(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "suggest-schedule-strict@example.com")
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
        "/semester-plans/suggest-schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"], "courseNumber": fixtures["courseANumber"]}],
            "maxCredits": 9,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cross_user_manual_plan_update_returns_404(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)

    owner_token = await register_access_token(auth_client, "manual-owner@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    other_token = await register_access_token(auth_client, "manual-other@example.com")
    response = await auth_client.put(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Hijack"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_plan_version_returns_404(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)

    owner_token = await register_access_token(auth_client, "version-owner@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    other_token = await register_access_token(auth_client, "version-other@example.com")
    response = await auth_client.post(
        f"/semester-plans/{plan_id}/versions",
        headers={"Authorization": f"Bearer {other_token}"},
        json={},
    )
    assert response.status_code == 404


async def _create_owner_plan(auth_client, mongo_database, *, owner_email: str):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    owner_token = await register_access_token(auth_client, owner_email)
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]
    return fixtures, owner_token, plan_id


@pytest.mark.asyncio
async def test_cross_user_plan_delete_returns_404(auth_client, mongo_database):
    _fixtures, _owner_token, plan_id = await _create_owner_plan(
        auth_client,
        mongo_database,
        owner_email="delete-owner@example.com",
    )
    other_token = await register_access_token(auth_client, "delete-other@example.com")

    response = await auth_client.delete(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_patch_planned_course_returns_404(auth_client, mongo_database):
    fixtures, _owner_token, plan_id = await _create_owner_plan(
        auth_client,
        mongo_database,
        owner_email="patch-course-owner@example.com",
    )
    other_token = await register_access_token(auth_client, "patch-course-other@example.com")

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{fixtures['courseANumber']}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"isActive": False},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_patch_lesson_selection_returns_404(auth_client, mongo_database):
    fixtures, _owner_token, plan_id = await _create_owner_plan(
        auth_client,
        mongo_database,
        owner_email="lesson-owner@example.com",
    )
    other_token = await register_access_token(auth_client, "lesson-other@example.com")

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{fixtures['courseANumber']}/lesson-selection",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"selectedLessonEvents": []},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_suggest_courses_enforces_rate_limit_with_429(
    progress_security_client,
    mongo_database,
):
    from tests.fixtures.suggest_courses_fixtures import seed_suggest_courses_offerings
    from tests.integration.test_semester_plans_integration import create_profile

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_suggest_courses_offerings(mongo_database)
    token = await register_access_token(progress_security_client, "suggest-rate@example.com")
    await create_profile(progress_security_client, token, degree_id=fixtures["programId"])

    payload = {"semesterCode": "2025-2", "maxCredits": 18}
    headers = {"Authorization": f"Bearer {token}"}

    first = await progress_security_client.post(
        "/semester-plans/suggest-courses",
        headers=headers,
        json=payload,
    )
    second = await progress_security_client.post(
        "/semester-plans/suggest-courses",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 429
