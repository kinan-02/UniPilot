"""Extensive integration tests for planner course/schedule suggestion endpoints."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.fixtures.suggest_courses_fixtures import seed_suggest_courses_offerings
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


async def _profile_and_token(auth_client, mongo_database, email: str, *, preferences: dict | None = None):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_suggest_courses_offerings(mongo_database)
    token = await register_access_token(auth_client, email)
    extra = {"preferences": preferences} if preferences else None
    await create_profile(auth_client, token, degree_id=fixtures["programId"], extra=extra)
    return fixtures, token


@pytest.mark.asyncio
async def test_suggest_courses_returns_matrix_semester_one_courses(auth_client, mongo_database):
    fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-matrix-sem1@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 18},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    numbers = [course["courseNumber"] for course in body["plannedCourses"]]
    assert fixtures["courseANumber"] in numbers
    assert fixtures["courseDNumber"] in numbers
    assert fixtures["courseENumber"] not in numbers
    assert len(numbers) == len(set(numbers))


@pytest.mark.asyncio
async def test_suggest_courses_respects_max_credits_and_sets_partial_plan(auth_client, mongo_database):
    fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-partial@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 5},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    explanation = body["explanation"]
    assert explanation["maxCredits"] == 5
    assert explanation["totalRecommendedCredits"] <= 5
    assert explanation["partialPlan"] is True
    assert explanation["emptyPlan"] is False
    assert explanation["selectedCount"] == len(body["plannedCourses"])
    assert "partialPlan" in explanation
    assert "emptyPlan" in explanation
    assert fixtures["courseANumber"] in [c["courseNumber"] for c in body["plannedCourses"]]


@pytest.mark.asyncio
async def test_suggest_courses_uses_profile_default_max_credits(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client,
        mongo_database,
        "suggest-profile-max@example.com",
        preferences={"maxCreditsPerSemester": 7},
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2"},
    )

    assert response.status_code == 200
    explanation = response.json()["data"]["explanation"]
    assert explanation["maxCredits"] == 7
    assert explanation["totalRecommendedCredits"] <= 7.5


@pytest.mark.asyncio
async def test_suggest_courses_after_semester_one_completion_moves_forward(auth_client, mongo_database):
    fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-progress@example.com"
    )

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
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )

    assert response.status_code == 200
    numbers = [course["courseNumber"] for course in response.json()["data"]["plannedCourses"]]
    assert fixtures["courseANumber"] not in numbers
    assert fixtures["courseDNumber"] not in numbers
    assert fixtures["courseENumber"] in numbers


@pytest.mark.asyncio
async def test_suggest_courses_includes_lesson_selections(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-lessons@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 8},
    )

    assert response.status_code == 200
    planned = response.json()["data"]["plannedCourses"]
    assert planned
    for course in planned:
        assert course.get("selectedLessonEvents")
        assert course["selectedLessonEvents"][0].get("eventId")


@pytest.mark.asyncio
async def test_suggest_courses_does_not_persist_plan(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-no-persist@example.com"
    )

    await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 9},
    )

    list_response = await auth_client.get(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.json()["data"]["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_suggest_courses_rejects_invalid_semester_code(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-bad-sem@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-9", "maxCredits": 6},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_courses_rejects_invalid_max_credits(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-bad-credits@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 2.3},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_schedule_rejects_invalid_semester_code(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-schedule-bad-sem@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-9",
            "plannedCourses": [
                {
                    "courseId": _fixtures["courseAId"],
                    "courseNumber": _fixtures["courseANumber"],
                }
            ],
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_schedule_rejects_empty_planned_courses(auth_client, mongo_database):
    _fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-schedule-empty@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "plannedCourses": []},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_schedule_rejects_all_inactive_courses(auth_client, mongo_database):
    fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-schedule-inactive@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "plannedCourses": [
                {
                    "courseId": fixtures["courseAId"],
                    "courseNumber": fixtures["courseANumber"],
                    "isActive": False,
                }
            ],
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_courses_service_validation_error_returns_400(auth_client, mongo_database):
    from unittest.mock import AsyncMock, patch

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "suggest-route-validation@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    with patch(
        "app.routes.semester_plans.suggest_semester_courses",
        new_callable=AsyncMock,
        return_value={"status": "validation_error", "errors": ["Invalid semesterCode"]},
    ):
        response = await auth_client.post(
            "/semester-plans/suggest-courses",
            headers={"Authorization": f"Bearer {token}"},
            json={"semesterCode": "2025-2", "maxCredits": 6},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_suggest_schedule_returns_conflict_free_selections(auth_client, mongo_database):
    fixtures, token = await _profile_and_token(
        auth_client, mongo_database, "suggest-schedule-ok@example.com"
    )

    response = await auth_client.post(
        "/semester-plans/suggest-schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesterCode": "2025-2",
            "plannedCourses": [
                {
                    "courseId": fixtures["courseAId"],
                    "courseNumber": fixtures["courseANumber"],
                    "courseTitle": "Discrete math",
                    "isActive": True,
                },
                {
                    "courseId": fixtures["courseDId"],
                    "courseNumber": fixtures["courseDNumber"],
                    "courseTitle": "Intro CS",
                    "isActive": True,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert len(body["selections"]) == 2
    assert body["examSummary"] is not None
    assert body["skippedCourses"] == []


@pytest.mark.asyncio
async def test_suggest_courses_without_offerings_returns_empty_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "suggest-no-offerings@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans/suggest-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["plannedCourses"] == []
    assert body["explanation"]["emptyPlan"] is True
    assert body["explanation"]["partialPlan"] is False
