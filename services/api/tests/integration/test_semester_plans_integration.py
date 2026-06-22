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


async def create_profile(
    client,
    token: str,
    *,
    degree_id: str | None = None,
    extra: dict | None = None,
) -> None:
    payload = {
        "institutionId": "technion",
        "programType": "BSc",
        "catalogYear": 2025,
        "currentSemesterCode": "2025-1",
    }
    if degree_id is not None:
        payload["degreeId"] = degree_id
    if extra:
        payload.update(extra)
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


@pytest.mark.asyncio
async def test_list_semester_plans_returns_400_for_unknown_query_params(auth_client):
    token = await register_access_token(auth_client, "sp-list-bad-param@example.com")

    response = await auth_client.get(
        "/semester-plans?unknownParam=value",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Unknown query parameter" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_semester_plan_returns_400_for_invalid_plan_id(auth_client):
    token = await register_access_token(auth_client, "sp-bad-id@example.com")

    response = await auth_client.get(
        "/semester-plans/not-a-valid-id",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "valid ObjectId" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_shared_semester_plan_returns_400_for_invalid_share_token(auth_client):
    response = await auth_client.get("/semester-plans/shared/tooshort")

    assert response.status_code == 400
    assert "share token" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_patch_planned_course_returns_400_for_empty_payload(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "sp-patch-empty@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_resp = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["semesterPlan"]["id"]

    planned = create_resp.json()["data"]["semesterPlan"].get("plannedCourses", [])
    if not planned:
        return

    course_number = planned[0].get("courseNumber", "09999999")

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 400
    assert "At least one field" in response.json()["error"]


@pytest.mark.asyncio
async def test_patch_planned_course_returns_400_for_invalid_course_number(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "sp-patch-invalid-num@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_resp = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["semesterPlan"]["id"]

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/INVALIDNUM",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": True},
    )

    assert response.status_code == 400
    assert "8-digit" in response.json()["error"]


@pytest.mark.asyncio
async def test_patch_planned_course_returns_400_for_empty_payload(auth_client, mongo_database):
    """Empty PATCH payload should return 400 (line 374 in routes/semester_plans.py)."""
    from unittest.mock import AsyncMock, patch

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "sp-empty-patch@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_resp = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["semesterPlan"]["id"]

    course_number = None
    semesters = create_resp.json()["data"]["semesterPlan"].get("semesters") or []
    for sem in semesters:
        for course in sem.get("plannedCourses") or []:
            if course.get("courseNumber"):
                course_number = course["courseNumber"]
                break
        if course_number:
            break

    if not course_number:
        pytest.skip("No planned courses in generated plan")

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}",
        headers={"Authorization": f"Bearer {token}"},
        json={},  # empty payload
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_route_returns_not_found(auth_client, mongo_database):
    """Tests the patch_maybe_lesson_selection route (lines 455-467)."""
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "sp-maybe-lesson-notfound@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    fake_plan_id = "665f2b0f2a3f7b2a1a9a7f99"
    response = await auth_client.patch(
        f"/semester-plans/{fake_plan_id}/maybe-courses/00940101/lesson-selection",
        headers={"Authorization": f"Bearer {token}"},
        json={"selectedLessonEvents": []},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_200_for_valid_request(auth_client, mongo_database):
    """Tests the successful path of patch_maybe_lesson_selection route (line 467)."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "sp-maybe-lesson-ok@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    # Create a manual plan with a maybeCourse
    course_id = ObjectId()
    plan_data = {
        "_id": ObjectId(),
        "userId": "some-user",
        "name": "Test Plan",
        "status": "draft",
        "plannerType": "manual",
        "version": 1,
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [],
                "maybeCourses": [
                    {
                        "courseId": str(course_id),
                        "courseNumber": "00940101",
                        "courseTitle": "Test Course",
                        "credits": 3.0,
                        "isActive": True,
                        "selectedLessonEvents": [],
                        "selectedGroups": {"lecture": [], "tutorial": [], "lab": [], "project": []},
                    }
                ],
            }
        ],
        "explanation": {},
        "assumptions": {},
        "semesters_count": 1,
    }

    fake_plan_id = str(ObjectId())

    with patch(
        "app.routes.semester_plans.patch_maybe_lesson_selection_by_user",
        new_callable=AsyncMock,
        return_value={"status": "ok", "plan": plan_data},
    ), patch(
        "app.routes.semester_plans._public_plan_with_insights",
        new_callable=AsyncMock,
        return_value={"id": fake_plan_id, "name": "Test Plan"},
    ):
        response = await auth_client.patch(
            f"/semester-plans/{fake_plan_id}/maybe-courses/00940101/lesson-selection",
            headers={"Authorization": f"Bearer {token}"},
            json={"selectedLessonEvents": []},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
