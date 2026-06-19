import pytest

VALID_PASSWORD = "StrongPass123!"


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_token(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "new-user@example.com",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "new-user@example.com"
    assert "accessToken" in body["data"]
    assert "passwordHash" not in body["data"]["user"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(auth_client):
    await auth_client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": VALID_PASSWORD,
        },
    )

    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email_with_different_casing(auth_client):
    await auth_client.post(
        "/auth/register",
        json={
            "email": "Duplicate@example.com",
            "password": VALID_PASSWORD,
        },
    )

    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "A user with this email already exists"


@pytest.mark.asyncio
async def test_login_returns_token_for_valid_credentials(auth_client):
    await auth_client.post(
        "/auth/register",
        json={
            "email": "login-user@example.com",
            "password": VALID_PASSWORD,
        },
    )

    response = await auth_client.post(
        "/auth/login",
        json={
            "email": "login-user@example.com",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "accessToken" in body["data"]
    assert body["data"]["user"]["email"] == "login-user@example.com"


@pytest.mark.asyncio
async def test_login_rejects_incorrect_password(auth_client):
    await auth_client.post(
        "/auth/register",
        json={
            "email": "wrong-password@example.com",
            "password": VALID_PASSWORD,
        },
    )

    response = await auth_client.post(
        "/auth/login",
        json={
            "email": "wrong-password@example.com",
            "password": "WrongPass123!",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user_for_valid_token(auth_client):
    register_response = await auth_client.post(
        "/auth/register",
        json={
            "email": "me-route@example.com",
            "password": VALID_PASSWORD,
        },
    )

    access_token = register_response.json()["data"]["accessToken"]

    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "me-route@example.com"
