"""Integration tests for lesson selection on semester plans."""

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import create_profile, register_access_token

from app.config import get_settings


def multi_group_schedule():
    return [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
        {"day": "Tuesday", "time": "12:30-14:30", "type": "lecture", "group": "20"},
        {"day": "Monday", "time": "10:30-11:30", "type": "tutorial", "group": "11"},
        {"day": "Wednesday", "time": "14:30-15:30", "type": "tutorial", "group": "12"},
    ]


async def seed_multi_group_offerings(database, *, course_a: str, course_b: str) -> None:
    settings = get_settings()
    await database[settings.course_offerings_collection].insert_many(
        [
            {
                "productionKey": f"technion:course-offering:{course_a}:2025:201",
                "courseNumber": course_a,
                "academicYear": 2025,
                "semesterCode": 201,
                "scheduleGroups": multi_group_schedule(),
                "status": "published",
            },
            {
                "productionKey": f"technion:course-offering:{course_b}:2025:201",
                "courseNumber": course_b,
                "academicYear": 2025,
                "semesterCode": 201,
                "scheduleGroups": [
                    {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
                ],
                "status": "published",
            },
        ]
    )


@pytest.mark.asyncio
async def test_add_course_with_no_selected_lessons(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_multi_group_offerings(
        mongo_database,
        course_a="00940345",
        course_b="00940411",
    )
    token = await register_access_token(auth_client, "lesson-none@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "No Lessons Yet",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    assert response.status_code == 201
    plan = response.json()["data"]["semesterPlan"]
    course = plan["semesters"][0]["plannedCourses"][0]
    assert course.get("selectedLessonEvents") in ([], None)
    weekly = plan["semesters"][0].get("weeklySchedule")
    assert weekly is None or not weekly.get("entries")
    warnings = plan["plannerInsights"].get("lessonSelectionWarnings") or []
    assert any(w["type"] == "no_lesson_selected" for w in warnings)


@pytest.mark.asyncio
async def test_patch_lesson_selection_persists(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_multi_group_offerings(
        mongo_database,
        course_a="00940345",
        course_b="00940411",
    )
    token = await register_access_token(auth_client, "lesson-select@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Select Lessons",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan = create_response.json()["data"]["semesterPlan"]
    plan_id = plan["id"]
    course_number = plan["semesters"][0]["plannedCourses"][0]["courseNumber"]

    from app.planning.lesson_events import extract_lesson_options_from_offering

    offering = {
        "courseNumber": course_number,
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": multi_group_schedule(),
    }
    options = extract_lesson_options_from_offering(offering)
    lecture = next(option for option in options if option["type"] == "lecture" and option["group"] == "10")
    tutorial = next(option for option in options if option["type"] == "tutorial" and option["group"] == "12")

    patch_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}/lesson-selection",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "selectedLessonEvents": [
                {"eventId": lecture["eventId"], "type": "lecture", "group": "10"},
                {"eventId": tutorial["eventId"], "type": "tutorial", "group": "12"},
            ]
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()["data"]["semesterPlan"]
    saved = patched["semesters"][0]["plannedCourses"][0]
    assert len(saved["selectedLessonEvents"]) == 2
    weekly = patched["semesters"][0]["weeklySchedule"]
    assert len(weekly["entries"]) == 1
    assert len(weekly["entries"][0]["scheduleGroups"]) == 2

    get_response = await auth_client.get(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    reloaded = get_response.json()["data"]["semesterPlan"]
    assert len(reloaded["semesters"][0]["plannedCourses"][0]["selectedLessonEvents"]) == 2


@pytest.mark.asyncio
async def test_invalid_lesson_event_rejected(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_multi_group_offerings(
        mongo_database,
        course_a="00940345",
        course_b="00940411",
    )
    token = await register_access_token(auth_client, "lesson-invalid@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Invalid Lesson",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]
    course_number = create_response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"][0][
        "courseNumber"
    ]

    patch_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}/lesson-selection",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "selectedLessonEvents": [
                {"eventId": "not-a-real-event", "type": "lecture", "group": "99"},
            ]
        },
    )
    assert patch_response.status_code == 400


@pytest.mark.asyncio
async def test_conflicts_use_selected_lessons_only(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_multi_group_offerings(
        mongo_database,
        course_a="00940345",
        course_b="00940411",
    )
    token = await register_access_token(auth_client, "lesson-conflicts@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Conflict Lessons",
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": fixtures["courseAId"]},
                {"courseId": fixtures["courseBId"]},
            ],
        },
    )
    plan = create_response.json()["data"]["semesterPlan"]
    plan_id = plan["id"]
    course_a_number = plan["semesters"][0]["plannedCourses"][0]["courseNumber"]
    course_b_number = plan["semesters"][0]["plannedCourses"][1]["courseNumber"]

    from app.planning.lesson_events import extract_lesson_options_from_offering

    options_a = extract_lesson_options_from_offering(
        {
            "courseNumber": course_a_number,
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": multi_group_schedule(),
        }
    )
    lecture_a = next(option for option in options_a if option["type"] == "lecture" and option["group"] == "10")

    options_b = extract_lesson_options_from_offering(
        {
            "courseNumber": course_b_number,
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [
                {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
            ],
        }
    )

    for course_number, events in (
        (course_a_number, [lecture_a]),
        (course_b_number, [options_b[0]]),
    ):
        await auth_client.patch(
            f"/semester-plans/{plan_id}/courses/{course_number}/lesson-selection",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "selectedLessonEvents": [
                    {
                        "eventId": events[0]["eventId"],
                        "type": events[0]["type"],
                        "group": events[0].get("group"),
                    }
                ]
            },
        )

    get_response = await auth_client.get(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    insights = get_response.json()["data"]["semesterPlan"]["plannerInsights"]
    assert len(insights["scheduleConflicts"]) >= 1


@pytest.mark.asyncio
async def test_lesson_selection_cross_user_isolation(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_multi_group_offerings(
        mongo_database,
        course_a="00940345",
        course_b="00940411",
    )
    owner_token = await register_access_token(auth_client, "lesson-owner@example.com")
    other_token = await register_access_token(auth_client, "lesson-other@example.com")
    await create_profile(auth_client, owner_token, degree_id=fixtures["programId"])
    await create_profile(auth_client, other_token, degree_id=fixtures["programId"])

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
    course_number = create_response.json()["data"]["semesterPlan"]["semesters"][0]["plannedCourses"][0][
        "courseNumber"
    ]

    patch_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/courses/{course_number}/lesson-selection",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"selectedLessonEvents": []},
    )
    assert patch_response.status_code == 404
