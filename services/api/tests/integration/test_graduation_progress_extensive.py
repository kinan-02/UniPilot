"""Extensive integration tests for GET /graduation-progress (Phases 15.0 + 15.1)."""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_extended_fixtures import seed_graduation_progress_15_1_fixtures
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


async def add_completed(
    client,
    token: str,
    course_id: str,
    *,
    grade: int | float = 82,
    credits: float = 3.5,
    attempt: int = 1,
    semester_code: str = "2024-1",
):
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
    return response


async def fetch_progress(client, token: str) -> dict:
    response = await client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]["graduationProgress"]


@pytest.mark.asyncio
async def test_phase_15_0_full_dds_scenario(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-15-0-full@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)
    await add_completed(auth_client, token, fixtures["courseCId"], credits=3.0)
    await add_completed(auth_client, token, fixtures["courseAId"], credits=4.0)

    progress = await fetch_progress(auth_client, token)

    assert progress["degreeCode"] == "009216-1-000"
    assert progress["totalRequiredCredits"] == 155.0
    assert progress["completedCredits"] == 10.5
    assert progress["statusSummary"] == "in_progress"
    assert len(progress["requirementProgress"]) == 3
    assert progress["assumptions"]
    assert isinstance(progress["ineligibleCredits"], list)

    ds = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":elective-ds"))
    faculty = next(r for r in progress["requirementProgress"] if "faculty" in r["requirementGroupId"])
    core = next(r for r in progress["requirementProgress"] if "core-mandatory" in r["requirementGroupId"])

    assert ds["creditsCompleted"] == 3.5
    assert ds["eligibilityEnforcement"] == "strict_pool"
    assert faculty["creditsCompleted"] == 3.0
    # Mandatory bucket credits = minCredits - remaining matrix slot credits (108 - 7).
    assert core["creditsCompleted"] == 101.0
    assert any(course["courseNumber"] == "00940345" for course in core["completedCourses"])


@pytest.mark.asyncio
async def test_phase_15_1_explicit_linked_pools(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_15_1_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-15-1-link@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseDsId"], credits=3.5)
    await add_completed(auth_client, token, fixtures["courseFacultyId"], credits=3.0)

    progress = await fetch_progress(auth_client, token)

    ds = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":elective-ds"))
    faculty = next(r for r in progress["requirementProgress"] if "faculty" in r["requirementGroupId"])

    assert ds["linkedPoolGroupId"] == "009216-1-000:custom-ds-pool"
    assert ds["creditsCompleted"] == 3.5
    assert faculty["linkedPoolGroupId"] == "009216-1-000:custom-faculty-pool"
    assert faculty["creditsCompleted"] == 3.0


@pytest.mark.asyncio
async def test_failing_grade_excluded_from_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-fail-grade@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json=build_completed_course_payload(
            fixtures["courseBId"],
            creditsEarned=0,
            semesterCode="2024-1",
            grade=40,
        ),
    )
    assert response.status_code == 201

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 0
    assert progress["statusSummary"] == "not_started"


@pytest.mark.asyncio
async def test_latest_failed_retake_removes_course_from_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-retake-fail@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], grade=88, credits=3.5, attempt=1)
    await add_completed(
        auth_client,
        token,
        fixtures["courseBId"],
        grade=40,
        credits=0,
        semester_code="2025-1",
        attempt=1,
    )

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 0


@pytest.mark.asyncio
async def test_retake_after_failed_attempt_counts_in_graduation_progress(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-retake-semester@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], grade=40, credits=0, attempt=1)
    second = await add_completed(
        auth_client,
        token,
        fixtures["courseBId"],
        grade=82,
        credits=3.5,
        semester_code="2025-1",
        attempt=1,
    )
    assert second.status_code == 201
    assert second.json()["data"]["completedCourse"]["attempt"] == 2

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 3.5


@pytest.mark.asyncio
async def test_retry_improves_effective_completion(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-retry@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseBId"], grade=40, credits=0, attempt=1)
    await add_completed(auth_client, token, fixtures["courseBId"], grade=82, credits=3.5, attempt=2)

    progress = await fetch_progress(auth_client, token)
    assert progress["completedCredits"] == 3.5


@pytest.mark.asyncio
async def test_non_pool_course_not_counted_in_ds_bucket(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-non-pool@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    await add_completed(auth_client, token, fixtures["courseAId"], credits=4.0)

    progress = await fetch_progress(auth_client, token)
    ds = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":elective-ds"))
    core = next(r for r in progress["requirementProgress"] if r["requirementGroupId"].endswith(":core-mandatory"))
    assert ds["creditsCompleted"] == 0
    # Mandatory bucket credits = minCredits - remaining matrix slot credits (108 - 7).
    assert core["creditsCompleted"] == 101.0
    assert progress["completedCredits"] == 4.0
    assert any(course["courseNumber"] == "00940345" for course in core["completedCourses"])
    assert not any(item["courseNumber"] == "00940345" for item in progress["ineligibleCredits"])


@pytest.mark.asyncio
async def test_degree_not_found_rejected_at_profile_create(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-bad-degree@example.com")

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


@pytest.mark.asyncio
async def test_user_isolation(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token_a = await register_access_token(auth_client, "ext-user-a@example.com")
    token_b = await register_access_token(auth_client, "ext-user-b@example.com")
    await create_profile(auth_client, token_a, fixtures["programId"])
    await create_profile(auth_client, token_b, fixtures["programId"])

    await add_completed(auth_client, token_a, fixtures["courseBId"], credits=3.5)

    progress_a = await fetch_progress(auth_client, token_a)
    progress_b = await fetch_progress(auth_client, token_b)

    assert progress_a["completedCredits"] == 3.5
    assert progress_b["completedCredits"] == 0


@pytest.mark.asyncio
async def test_missing_requirements_structure(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-missing-req@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    progress = await fetch_progress(auth_client, token)
    assert len(progress["missingRequirements"]) == len(progress["requirementProgress"])
    for item in progress["missingRequirements"]:
        assert "creditsRequired" in item
        assert "eligibilityEnforcement" in item
        assert item["status"] != "satisfied"


@pytest.mark.asyncio
async def test_concurrent_graduation_progress_requests(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-concurrent@example.com")
    await create_profile(auth_client, token, fixtures["programId"])
    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)

    async def one_request():
        return await auth_client.get(
            "/graduation-progress",
            headers={"Authorization": f"Bearer {token}"},
        )

    responses = await asyncio.gather(*[one_request() for _ in range(20)])
    for response in responses:
        assert response.status_code == 200
        assert response.json()["data"]["graduationProgress"]["completedCredits"] == 3.5


@pytest.mark.asyncio
async def test_graduation_progress_latency_under_threshold(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "ext-perf@example.com")
    await create_profile(auth_client, token, fixtures["programId"])
    await add_completed(auth_client, token, fixtures["courseBId"], credits=3.5)

    samples_ms: list[float] = []
    for _ in range(30):
        start = time.perf_counter()
        response = await auth_client.get(
            "/graduation-progress",
            headers={"Authorization": f"Bearer {token}"},
        )
        elapsed = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        samples_ms.append(elapsed)

    p50 = sorted(samples_ms)[len(samples_ms) // 2]
    assert p50 < 500, f"p50 latency {p50:.1f}ms exceeds 500ms threshold (in-memory test env)"
