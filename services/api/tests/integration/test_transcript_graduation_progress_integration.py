"""Integration tests: transcript (completed courses) ↔ graduation progress."""

from __future__ import annotations

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


async def create_profile(client, token: str, program_id: str) -> None:
    response = await client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    assert response.status_code == 201


async def fetch_progress(client, token: str) -> dict:
    response = await client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]["graduationProgress"]


async def add_completed(
    client,
    token: str,
    course_id: str,
    *,
    grade: int | float = 82,
    credits: float = 3.5,
    semester_code: str = "2024-1",
    attempt: int = 1,
) -> dict:
    response = await client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json=build_completed_course_payload(
            course_id,
            creditsEarned=credits,
            semesterCode=semester_code,
            grade=grade,
            attempt=attempt,
        ),
    )
    assert response.status_code == 201
    return response.json()["data"]["completedCourse"]


def bucket_by_suffix(progress: dict, suffix: str) -> dict:
    return next(
        bucket
        for bucket in progress["requirementProgress"]
        if bucket["requirementGroupId"].endswith(f":{suffix}")
    )


def progress_course_numbers(progress: dict) -> set[str]:
    numbers: set[str] = set()
    for bucket in progress["requirementProgress"]:
        for course in bucket.get("completedCourses", []):
            number = course.get("courseNumber")
            if number:
                numbers.add(number)
    return numbers


@pytest.mark.asyncio
async def test_add_completed_course_updates_progress_totals_and_bucket(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-add@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    before = await fetch_progress(auth_client, token)
    assert before["completedCredits"] == 0
    assert before["statusSummary"] == "not_started"

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)

    after = await fetch_progress(auth_client, token)
    assert after["completedCredits"] == 3.5
    assert after["statusSummary"] == "in_progress"
    assert after["completionPercentage"] > 0

    ds = bucket_by_suffix(after, "elective-ds")
    assert ds["creditsCompleted"] == 3.5
    assert any(
        course["courseNumber"] == fixtures["courseBNumber"]
        for course in ds["completedCourses"]
    )


@pytest.mark.asyncio
async def test_delete_completed_course_reverts_graduation_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-delete@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    record = await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)
    progress_with_course = await fetch_progress(auth_client, token)
    assert progress_with_course["completedCredits"] == 3.5

    delete_response = await auth_client.delete(
        f"/completed-courses/{record['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 200

    progress_after_delete = await fetch_progress(auth_client, token)
    assert progress_after_delete["completedCredits"] == 0
    assert progress_after_delete["statusSummary"] == "not_started"
    assert fixtures["courseBNumber"] not in progress_course_numbers(progress_after_delete)


@pytest.mark.asyncio
async def test_update_grade_from_pass_to_fail_excludes_course(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-pass-fail@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    record = await add_completed(auth_client, token, fixtures["courseBId"], grade=85, credits=3.5)
    assert (await fetch_progress(auth_client, token))["completedCredits"] == 3.5

    update_response = await auth_client.put(
        f"/completed-courses/{record['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"grade": 40, "creditsEarned": 0},
    )
    assert update_response.status_code == 200

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 0
    ds = bucket_by_suffix(progress, "elective-ds")
    assert ds["creditsCompleted"] == 0


@pytest.mark.asyncio
async def test_update_grade_from_fail_to_pass_includes_course(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-fail-pass@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    record = await add_completed(
        auth_client,
        token,
        fixtures["courseBId"],
        grade=40,
        credits=0,
    )
    assert (await fetch_progress(auth_client, token))["completedCredits"] == 0

    update_response = await auth_client.put(
        f"/completed-courses/{record['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"grade": 88, "creditsEarned": 3.5},
    )
    assert update_response.status_code == 200

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 3.5
    assert fixtures["courseBNumber"] in progress_course_numbers(progress)


@pytest.mark.asyncio
async def test_multi_year_semester_codes_all_contribute_to_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-multi-year@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(
        auth_client,
        token,
        fixtures["courseBId"],
        credits=3.5,
        semester_code="2019-2",
    )
    await add_completed(
        auth_client,
        token,
        fixtures["courseCId"],
        credits=3.0,
        semester_code="2022-1",
    )
    await add_completed(
        auth_client,
        token,
        fixtures["courseAId"],
        credits=4.0,
        semester_code="2025-1",
    )

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 10.5

    list_response = await auth_client.get(
        "/completed-courses?limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    semesters = {item["semesterCode"] for item in list_response.json()["data"]["completedCourses"]}
    assert semesters == {"2019-2", "2022-1", "2025-1"}


@pytest.mark.asyncio
async def test_strict_pool_course_in_bucket_ineligible_course_in_separate_list(
    auth_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-pool-vs-ineligible@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)
    await add_completed(auth_client, token, fixtures["courseAId"], credits=4.0)

    progress = await fetch_progress(auth_client, token)
    ds = bucket_by_suffix(progress, "elective-ds")
    core = bucket_by_suffix(progress, "core-mandatory")

    assert fixtures["courseBNumber"] in progress_course_numbers(progress)
    assert any(course["courseNumber"] == fixtures["courseBNumber"] for course in ds["completedCourses"])
    assert any(
        course["courseNumber"] == fixtures["courseANumber"] for course in core["completedCourses"]
    )
    assert fixtures["courseANumber"] not in {
        course["courseNumber"] for course in ds["completedCourses"]
    }
    assert not any(
        item["courseNumber"] == fixtures["courseANumber"] for item in progress["ineligibleCredits"]
    )


@pytest.mark.asyncio
async def test_delete_and_readd_restores_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-readd@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    record = await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)
    assert (await fetch_progress(auth_client, token))["completedCredits"] == 3.5

    await auth_client.delete(
        f"/completed-courses/{record['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert (await fetch_progress(auth_client, token))["completedCredits"] == 0

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5, attempt=2)
    restored = await fetch_progress(auth_client, token)
    assert restored["completedCredits"] == 3.5
    assert fixtures["courseBNumber"] in progress_course_numbers(restored)


@pytest.mark.asyncio
async def test_transcript_list_aligns_with_progress_passing_courses(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-list-align@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)
    await add_completed(auth_client, token, fixtures["courseAId"], grade=40, credits=0)

    progress = await fetch_progress(auth_client, token)
    list_response = await auth_client.get(
        "/completed-courses?limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    listed_numbers = {
        item["courseNumber"]
        for item in list_response.json()["data"]["completedCourses"]
    }

    assert listed_numbers == {fixtures["courseBNumber"], fixtures["courseANumber"]}
    assert progress["completedCredits"] == 3.5
    assert fixtures["courseBNumber"] in progress_course_numbers(progress)
    ds = bucket_by_suffix(progress, "elective-ds")
    assert ds["creditsCompleted"] == 3.5
    core = bucket_by_suffix(progress, "core-mandatory")
    assert core["creditsCompleted"] == 0


@pytest.mark.asyncio
async def test_curriculum_graph_reflects_transcript_backed_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "txgp-curriculum@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)

    graph_response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert graph_response.status_code == 200
    graph = graph_response.json()["data"]["curriculumGraph"]
    assert graph["programCode"] == "009216-1-000"
    assert isinstance(graph.get("electiveBuckets"), list)
    assert len(graph["electiveBuckets"]) > 0
