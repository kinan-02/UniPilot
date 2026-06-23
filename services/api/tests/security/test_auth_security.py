import pytest

VALID_PASSWORD = "StrongPass123!"


@pytest.mark.asyncio
async def test_me_returns_401_when_missing_token(security_client):
    response = await security_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"] == "Authentication token is required"


@pytest.mark.asyncio
async def test_me_returns_401_when_token_is_invalid(security_client):
    response = await security_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "Authentication token is invalid or expired"


@pytest.mark.asyncio
async def test_me_succeeds_with_valid_token(security_client):
    register_response = await security_client.post(
        "/auth/register",
        json={
            "email": "security-user@example.com",
            "password": VALID_PASSWORD,
        },
    )

    access_token = register_response.json()["data"]["accessToken"]

    response = await security_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "security-user@example.com"


@pytest.mark.asyncio
async def test_register_response_never_exposes_password_hash(security_client):
    response = await security_client.post(
        "/auth/register",
        json={
            "email": "hash-check@example.com",
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 201
    assert "passwordHash" not in response.text


@pytest.mark.asyncio
async def test_auth_routes_enforce_rate_limiting_with_429(security_client):
    await security_client.post(
        "/auth/register",
        json={
            "email": "security-user@example.com",
            "password": VALID_PASSWORD,
        },
    )

    await security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": "WrongPass123!",
        },
    )

    await security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": "WrongPass123!",
        },
    )

    limited_response = await security_client.post(
        "/auth/login",
        json={
            "email": "security-user@example.com",
            "password": "WrongPass123!",
        },
    )

    assert limited_response.status_code == 429
    assert limited_response.json()["error"] == (
        "Too many authentication requests. Please try again later."
    )


@pytest.mark.asyncio
async def test_refresh_endpoint_enforces_rate_limit(security_client):
    await security_client.post(
        "/auth/register",
        json={"email": "refresh-rate-limit@example.com", "password": VALID_PASSWORD},
    )

    for _ in range(2):
        await security_client.post("/auth/refresh")

    limited_response = await security_client.post("/auth/refresh")
    assert limited_response.status_code == 429
