"""Integration: transcript PDF commit flows into graduation progress buckets."""

from __future__ import annotations

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


def bucket_by_suffix(progress: dict, suffix: str) -> dict:
    return next(
        bucket
        for bucket in progress["requirementProgress"]
        if bucket["requirementGroupId"].endswith(f":{suffix}")
    )


@pytest.mark.asyncio
async def test_transcript_import_commit_assigns_mandatory_and_elective_buckets(
    auth_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "tx-import-gp@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": fixtures["courseANumber"],
                    "semesterCode": "2024-1",
                    "grade": 88,
                    "creditsEarned": 4.0,
                },
                {
                    "courseNumber": fixtures["courseBNumber"],
                    "semesterCode": "2024-2",
                    "grade": 85,
                    "creditsEarned": 3.5,
                },
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["importResult"]["createdCount"] == 2

    progress_response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    progress = progress_response.json()["data"]["graduationProgress"]
    core = bucket_by_suffix(progress, "core-mandatory")
    ds = bucket_by_suffix(progress, "elective-ds")

    assert any(
        course["courseNumber"] == fixtures["courseANumber"] for course in core["completedCourses"]
    )
    assert any(
        course["courseNumber"] == fixtures["courseBNumber"] for course in ds["completedCourses"]
    )
    assert fixtures["courseANumber"] not in {
        course["courseNumber"] for course in ds["completedCourses"]
    }
    assert progress["remainingMandatoryCourses"]
    assert any(
        course["courseNumber"] == fixtures["courseENumber"]
        for course in progress["remainingMandatoryCourses"]
    )
    assert progress["ineligibleCredits"] == []


@pytest.mark.asyncio
async def test_transcript_import_commit_accepts_unpadded_course_numbers(
    auth_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "tx-import-unpadded@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    unpadded = fixtures["courseBNumber"][1:]
    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": unpadded,
                    "semesterCode": "2024-2",
                    "grade": 85,
                    "creditsEarned": 3.5,
                }
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]["importResult"]
    assert payload["createdCount"] == 1
    assert payload["unresolvedCount"] == 0
