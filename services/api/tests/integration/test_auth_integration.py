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


@pytest.mark.asyncio
async def test_login_rejects_email_that_does_not_exist(auth_client):
    response = await auth_client.post(
        "/auth/login",
        json={
            "email": "ghost@example.com",
            "password": VALID_PASSWORD,
        },
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["error"]


@pytest.mark.asyncio
async def test_me_returns_401_for_token_with_deleted_user(auth_client, monkeypatch):
    """A valid JWT for a non-existent user_id should return 401 on /me."""
    from app.security.jwt import create_access_token

    token = create_access_token(
        user_id="deadbeefdeadbeefdeadbeef",
        email="ghost@example.com",
    )

    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert "invalid or expired" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_register_rejects_weak_password(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "weak-pass@example.com",
            "password": "weak",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_me_returns_401_without_token(auth_client):
    response = await auth_client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_duplicate_key_error_returns_409(auth_client, monkeypatch):
    """Simulate a race condition where create_user raises DuplicateKeyError."""
    from unittest.mock import AsyncMock, patch
    from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

    await auth_client.post(
        "/auth/register",
        json={"email": "first-register@example.com", "password": VALID_PASSWORD},
    )

    with patch(
        "app.routes.auth.create_user",
        new_callable=AsyncMock,
        side_effect=MongoDuplicateKeyError(""),
    ):
        response = await auth_client.post(
            "/auth/register",
            json={"email": "race-condition@example.com", "password": VALID_PASSWORD},
        )

    assert response.status_code == 409
    assert "already exists" in response.json()["error"]
