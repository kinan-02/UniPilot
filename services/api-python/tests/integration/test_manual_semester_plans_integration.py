import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    VALID_PASSWORD,
    create_profile,
    register_access_token,
)

from app.config import get_settings


async def seed_course_offerings(database, *, course_number: str, course_id: str) -> None:
    settings = get_settings()
    await database[settings.course_offerings_collection].insert_many(
        [
            {
                "productionKey": f"technion:course-offering:{course_number}:2025:201",
                "courseNumber": course_number,
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30", "type": "lecture"}],
                "status": "published",
            },
            {
                "productionKey": f"technion:course-offering:00940411:2025:201",
                "courseNumber": "00940411",
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30", "type": "lecture"}],
                "status": "published",
            },
        ]
    )


@pytest.mark.asyncio
async def test_create_manual_semester_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "manual-plan-create@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "My Spring Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": fixtures["courseAId"]},
                {"courseId": fixtures["courseBId"]},
            ],
        },
    )

    assert response.status_code == 201
    plan = response.json()["data"]["semesterPlan"]
    assert plan["plannerType"] == "manual"
    assert len(plan["semesters"][0]["plannedCourses"]) == 2
    assert plan["semesters"][0]["plannedCourses"][0]["courseNumber"]


@pytest.mark.asyncio
async def test_update_manual_semester_plan_adds_weekly_schedule(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_course_offerings(
        mongo_database,
        course_number="00940345",
        course_id=fixtures["courseAId"],
    )
    token = await register_access_token(auth_client, "manual-plan-update@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Schedule Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": fixtures["courseAId"]},
                {"courseId": fixtures["courseBId"]},
            ],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    update_response = await auth_client.put(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "semesters": [
                {
                    "semesterCode": "2025-2",
                    "plannedCourses": [
                        {"courseId": fixtures["courseAId"]},
                        {"courseId": fixtures["courseBId"]},
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
                }
            ]
        },
    )

    assert update_response.status_code == 200
    plan = update_response.json()["data"]["semesterPlan"]
    weekly = plan["semesters"][0]["weeklySchedule"]
    assert weekly["status"] == "conflicts"
    assert len(weekly["entries"]) == 2
    assert len(weekly["conflicts"]) == 1
    assert plan["version"] == 2


@pytest.mark.asyncio
async def test_archive_manual_semester_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "manual-plan-archive@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Archive Me",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    delete_response = await auth_client.delete(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["semesterPlan"]["status"] == "archived"

    update_response = await auth_client.put(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Should Fail"},
    )
    assert update_response.status_code == 400


@pytest.mark.asyncio
async def test_manual_plan_rejects_unknown_course(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "manual-plan-invalid@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bad Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": "665f2b0f2a3f7b2a1a9a7fff"}],
        },
    )

    assert response.status_code == 400
