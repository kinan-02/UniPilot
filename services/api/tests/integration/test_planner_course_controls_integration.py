"""Integration tests for planned course toggle and reorder."""

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    VALID_PASSWORD,
    create_profile,
    register_access_token,
)

from app.config import get_settings


async def seed_course_offerings(database, *, course_number: str) -> None:
    settings = get_settings()
    await database[settings.course_offerings_collection].insert_many(
        [
            {
                "productionKey": f"technion:course-offering:{course_number}:2025:201",
                "courseNumber": course_number,
                "academicYear": 2025,
                "semesterCode": 201,
                "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30", "type": "lecture"}],
                "examDates": {"moedA": "2025-06-01 09:00", "moedB": "2025-07-15 09:00"},
                "status": "published",
            },
            {
                "productionKey": "technion:course-offering:00940411:2025:201",
                "courseNumber": "00940411",
                "academicYear": 2025,
                "semesterCode": 201,
                "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30", "type": "lecture"}],
                "examDates": {"moedA": "2025-06-01 10:00"},
                "status": "published",
            },
        ]
    )


@pytest.mark.asyncio
async def test_patch_course_toggle_inactive_excludes_credits_and_conflicts(
    auth_client, mongo_database
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_course_offerings(mongo_database, course_number="00940345")
    token = await register_access_token(auth_client, "toggle-inactive@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Toggle Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": fixtures["courseAId"], "isActive": True},
                {"courseId": fixtures["courseBId"], "isActive": True},
            ],
            "weeklySchedule": {
                "entries": [
                    {
                        "courseId": fixtures["courseAId"],
                        "academicYear": 2025,
                        "semesterCode": 201,
                    },
                    {
                        "courseId": fixtures["courseBId"],
                        "academicYear": 2025,
                        "semesterCode": 201,
                    },
                ]
            },
        },
    )
    assert create_response.status_code == 201
    plan = create_response.json()["data"]["semesterPlan"]
    plan_id = plan["id"]
    course_number = plan["semesters"][0]["plannedCourses"][0]["courseNumber"]
    assert plan["plannerInsights"]["totalCredits"] > 0
    assert len(plan["plannerInsights"]["scheduleConflicts"]) >= 1

    patch_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": False},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()["data"]["semesterPlan"]
    inactive = next(
        c for c in patched["semesters"][0]["plannedCourses"] if c["courseNumber"] == course_number
    )
    assert inactive["isActive"] is False
    insights = patched["plannerInsights"]
    assert insights["activeCourseCount"] == 1
    assert insights["totalCredits"] < plan["plannerInsights"]["totalCredits"]
    assert len(insights["scheduleConflicts"]) == 0
    exam_numbers = {exam["courseNumber"] for exam in insights["examSummary"]["exams"]}
    assert course_number not in exam_numbers


@pytest.mark.asyncio
async def test_reorder_planned_courses_persists(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "reorder-courses@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Reorder Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": fixtures["courseAId"]},
                {"courseId": fixtures["courseBId"]},
            ],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]
    original = create_response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"]
    reversed_ids = [original[1]["courseId"], original[0]["courseId"]]

    reorder_response = await auth_client.put(
        f"/semester-plans/{plan_id}/courses/order",
        headers={"Authorization": f"Bearer {token}"},
        json={"courseIds": reversed_ids},
    )
    assert reorder_response.status_code == 200
    reordered = reorder_response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"]
    assert [course["courseId"] for course in reordered] == reversed_ids

    get_response = await auth_client.get(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    persisted = get_response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"]
    assert [course["courseId"] for course in persisted] == reversed_ids
