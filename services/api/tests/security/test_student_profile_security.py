import pytest

VALID_PASSWORD = "StrongPass123!"

PROFILE_PAYLOAD = {
    "institutionId": "uni-main-A",
    "programType": "BSc-A",
    "catalogYear": 2024,
    "currentSemesterCode": "2024-1",
}


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_get_profile_returns_401_when_missing_token(security_client):
    response = await security_client.get("/student-profile")

    assert response.status_code == 401
    assert response.json()["error"] == "Authentication token is required"


@pytest.mark.asyncio
async def test_create_profile_returns_401_when_missing_token(security_client):
    response = await security_client.post("/student-profile", json=PROFILE_PAYLOAD)

    assert response.status_code == 401
    assert response.json()["error"] == "Authentication token is required"


@pytest.mark.asyncio
async def test_create_profile_returns_401_with_invalid_token(security_client):
    response = await security_client.post(
        "/student-profile",
        headers={"Authorization": "Bearer invalid.jwt.token"},
        json=PROFILE_PAYLOAD,
    )

    assert response.status_code == 401
    assert response.json()["error"] == "Authentication token is invalid or expired"


@pytest.mark.asyncio
async def test_user_a_only_reads_own_profile(security_client):
    access_token_a = await register_access_token(security_client, "userA@example.com")
    access_token_b = await register_access_token(security_client, "userB@example.com")

    create_a = await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
        json=PROFILE_PAYLOAD,
    )
    profile_id_a = create_a.json()["data"]["profile"]["id"]

    create_b = await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_b}"},
        json={
            "institutionId": "uni-main-B",
            "programType": "BSc-B",
            "catalogYear": 2024,
            "currentSemesterCode": "2024-1",
        },
    )
    profile_id_b = create_b.json()["data"]["profile"]["id"]

    response = await security_client.get(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["profile"]["id"] == profile_id_a
    assert response.json()["data"]["profile"]["id"] != profile_id_b


@pytest.mark.asyncio
async def test_create_rejects_user_id_in_request_body(security_client):
    access_token = await register_access_token(security_client, "userid-reject@example.com")

    response = await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            **PROFILE_PAYLOAD,
            "userId": "665f2b0f2a3f7b2a1a9a7f10",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_rejects_id_in_request_body(security_client):
    access_token_a = await register_access_token(security_client, "update-reject-a@example.com")
    access_token_b = await register_access_token(security_client, "update-reject-b@example.com")

    await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
        json=PROFILE_PAYLOAD,
    )

    create_b = await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_b}"},
        json={
            "institutionId": "uni-main-B",
            "programType": "BSc-B",
            "catalogYear": 2024,
            "currentSemesterCode": "2024-1",
        },
    )
    profile_id_b = create_b.json()["data"]["profile"]["id"]

    response = await security_client.put(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
        json={
            "_id": profile_id_b,
            "programType": "BSc-Honors",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_deleting_user_a_profile_does_not_remove_user_b_profile(security_client):
    access_token_a = await register_access_token(security_client, "delete-a@example.com")
    access_token_b = await register_access_token(security_client, "delete-b@example.com")

    await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
        json=PROFILE_PAYLOAD,
    )

    create_b = await security_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_b}"},
        json={
            "institutionId": "uni-main-B",
            "programType": "BSc-B",
            "catalogYear": 2024,
            "currentSemesterCode": "2024-1",
        },
    )
    profile_id_b = create_b.json()["data"]["profile"]["id"]

    delete_response = await security_client.delete(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_a}"},
    )
    assert delete_response.status_code == 200

    user_b_profile_response = await security_client.get(
        "/student-profile",
        headers={"Authorization": f"Bearer {access_token_b}"},
    )

    assert user_b_profile_response.status_code == 200
    assert user_b_profile_response.json()["data"]["profile"]["id"] == profile_id_b
