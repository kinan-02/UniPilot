"""Student-profile edge cases (validation, lifecycle, degree binding)."""

from __future__ import annotations

import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"

PROFILE_PAYLOAD = {
    "institutionId": "uni-main",
    "programType": "BSc",
    "catalogYear": 2025,
    "currentSemesterCode": "2025-1",
}


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_create_profile_rejects_malformed_degree_id(auth_client):
    token = await register_access_token(auth_client, "profile-malformed-degree@example.com")

    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={**PROFILE_PAYLOAD, "degreeId": "not-a-valid-object-id"},
    )

    assert response.status_code == 400
    assert "objectid" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_update_profile_rejects_malformed_degree_id(auth_client):
    token = await register_access_token(auth_client, "profile-update-malformed-degree@example.com")

    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json=PROFILE_PAYLOAD,
    )

    response = await auth_client.put(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"degreeId": "12345"},
    )

    assert response.status_code == 400
    assert "objectid" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_create_profile_rejects_nonexistent_degree_id(auth_client):
    token = await register_access_token(auth_client, "profile-edge-missing-degree@example.com")

    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={**PROFILE_PAYLOAD, "degreeId": "665f2b0f2a3f7b2a1a9a7fff"},
    )

    assert response.status_code == 400
    assert "degree program" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_duplicate_profile_create_returns_409(auth_client):
    token = await register_access_token(auth_client, "profile-edge-duplicate@example.com")

    first = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json=PROFILE_PAYLOAD,
    )
    assert first.status_code == 201

    duplicate = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json=PROFILE_PAYLOAD,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "Student profile already exists for this user"


@pytest.mark.asyncio
async def test_profile_can_be_recreated_after_delete(auth_client):
    token = await register_access_token(auth_client, "profile-edge-recreate@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await auth_client.post("/student-profile", headers=headers, json=PROFILE_PAYLOAD)
    assert create_response.status_code == 201
    first_id = create_response.json()["data"]["profile"]["id"]

    delete_response = await auth_client.delete("/student-profile", headers=headers)
    assert delete_response.status_code == 200

    recreate_response = await auth_client.post(
        "/student-profile",
        headers=headers,
        json={**PROFILE_PAYLOAD, "programType": "BSc-Second"},
    )
    assert recreate_response.status_code == 201
    second_id = recreate_response.json()["data"]["profile"]["id"]
    assert second_id != first_id
    assert recreate_response.json()["data"]["profile"]["programType"] == "BSc-Second"


@pytest.mark.asyncio
async def test_update_profile_rejects_empty_body(auth_client):
    token = await register_access_token(auth_client, "profile-edge-empty-update@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await auth_client.post("/student-profile", headers=headers, json=PROFILE_PAYLOAD)

    response = await auth_client.put("/student-profile", headers=headers, json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_profile_rejects_nonexistent_degree_id(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "profile-edge-update-degree@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await auth_client.post(
        "/student-profile",
        headers=headers,
        json={**PROFILE_PAYLOAD, "degreeId": fixtures["programId"]},
    )

    response = await auth_client.put(
        "/student-profile",
        headers=headers,
        json={"degreeId": "665f2b0f2a3f7b2a1a9a7fff"},
    )
    assert response.status_code == 400
    assert "degree program" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_create_profile_with_valid_academic_path(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "profile-academic-path@example.com")

    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            **PROFILE_PAYLOAD,
            "degreeId": fixtures["programId"],
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    assert response.status_code == 201
    assert (
        response.json()["data"]["profile"]["academicPath"]["trackSlug"]
        == "track-data-information-engineering"
    )


@pytest.mark.asyncio
async def test_update_profile_with_valid_academic_path(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "profile-update-path@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await auth_client.post(
        "/student-profile",
        headers=headers,
        json={**PROFILE_PAYLOAD, "degreeId": fixtures["programId"]},
    )

    response = await auth_client.put(
        "/student-profile",
        headers=headers,
        json={"academicPath": {"trackSlug": "track-data-information-engineering"}},
    )
    assert response.status_code == 200
    assert (
        response.json()["data"]["profile"]["academicPath"]["trackSlug"]
        == "track-data-information-engineering"
    )
