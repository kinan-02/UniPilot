"""Integration tests for transcript import commit."""

import pytest

from tests.fixtures.completed_course_fixtures import seed_production_course_fixture

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_transcript_import_commit_requires_auth(auth_client):
    response = await auth_client.post(
        "/transcript-import/commit",
        json={
            "courses": [
                {
                    "courseNumber": "00960401",
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                }
            ]
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_transcript_import_commit_creates_imported_records(auth_client, mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    token = await register_access_token(auth_client, "transcript-commit@example.com")

    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": course["courseNumber"],
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                    "title": "Imported course",
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["importResult"]
    assert payload["createdCount"] == 1
    assert payload["created"][0]["source"] == "imported"
    assert payload["created"][0]["semesterCode"] == "2024-1"


@pytest.mark.asyncio
async def test_transcript_import_commit_reports_unresolved_catalog(auth_client):
    token = await register_access_token(auth_client, "transcript-unresolved@example.com")

    response = await auth_client.post(
        "/transcript-import/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "courses": [
                {
                    "courseNumber": "00000000",
                    "semesterCode": "2024-1",
                    "grade": 85,
                    "creditsEarned": 3,
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["importResult"]
    assert payload["createdCount"] == 0
    assert payload["unresolvedCount"] == 1
    assert payload["unresolved"][0]["courseNumber"] == "00000000"
