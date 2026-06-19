import pytest

VALID_PASSWORD = "StrongPass123!"

PROFILE_PAYLOAD = {
    "institutionId": "uni-main",
    "programType": "BSc",
    "catalogYear": 2025,
    "currentSemesterCode": "2025-1",
    "preferences": {
        "maxCreditsPerSemester": 18,
    },
}


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_get_profile_returns_404_when_profile_does_not_exist(auth_client):
    access_token = await register_access_token(auth_client, "profile-missing@example.com")

    response = await auth_client.get(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "Student profile not found"


@pytest.mark.asyncio
async def test_put_returns_404_when_profile_does_not_exist(auth_client):
    access_token = await register_access_token(auth_client, "profile-put-missing@example.com")

    response = await auth_client.put(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"programType": "BSc-Honors"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "Student profile not found"


@pytest.mark.asyncio
async def test_delete_returns_404_when_profile_does_not_exist(auth_client):
    access_token = await register_access_token(auth_client, "profile-delete-missing@example.com")

    response = await auth_client.delete(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "Student profile not found"


@pytest.mark.asyncio
async def test_create_profile_for_authenticated_user(auth_client):
    register_response = await auth_client.post(
        "/auth/register",
        json={"email": "profile-owner@example.com", "password": VALID_PASSWORD},
    )
    assert register_response.status_code == 201
    access_token = register_response.json()["data"]["accessToken"]
    owner_user_id = register_response.json()["data"]["user"]["id"]

    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["profile"]["institutionId"] == "uni-main"
    assert body["data"]["profile"]["userId"] == owner_user_id
    assert "passwordHash" not in response.text


@pytest.mark.asyncio
async def test_create_profile_returns_409_for_duplicate_profile(auth_client):
    access_token = await register_access_token(auth_client, "duplicate-profile@example.com")

    first_response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )
    assert first_response.status_code == 201

    duplicate_response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"] == "Student profile already exists for this user"


@pytest.mark.asyncio
async def test_get_profile_returns_authenticated_users_profile(auth_client):
    access_token = await register_access_token(auth_client, "profile-get@example.com")

    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )

    response = await auth_client.get(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["profile"]["programType"] == "BSc"


@pytest.mark.asyncio
async def test_update_profile_for_authenticated_user(auth_client):
    access_token = await register_access_token(auth_client, "profile-update@example.com")

    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )

    response = await auth_client.put(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "programType": "BSc-Honors",
            "currentSemesterCode": "2025-2",
            "preferences": {"maxCreditsPerSemester": 21},
        },
    )

    assert response.status_code == 200
    profile = response.json()["data"]["profile"]
    assert profile["programType"] == "BSc-Honors"
    assert profile["currentSemesterCode"] == "2025-2"
    assert profile["revision"] == 2


@pytest.mark.asyncio
async def test_delete_profile_removes_current_user_profile(auth_client):
    access_token = await register_access_token(auth_client, "profile-delete@example.com")

    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json=PROFILE_PAYLOAD,
    )

    delete_response = await auth_client.delete(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True

    get_response = await auth_client.get(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_create_profile_accepts_optional_degree_id_without_catalog_validation(auth_client):
    access_token = await register_access_token(auth_client, "profile-degree@example.com")

    response = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            **PROFILE_PAYLOAD,
            "degreeId": "665f2b0f2a3f7b2a1a9a7f11",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["profile"]["degreeId"] == "665f2b0f2a3f7b2a1a9a7f11"
