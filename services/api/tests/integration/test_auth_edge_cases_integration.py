"""HTTP integration edge cases for auth sessions, tokens, and refresh rotation."""

from __future__ import annotations

import time

import pytest
from bson import ObjectId

from app.config import get_settings
from app.security.cookies import REFRESH_TOKEN_COOKIE
from app.security.jwt import create_access_token

VALID_PASSWORD = "StrongPass123!"


@pytest.mark.asyncio
async def test_refresh_rejects_reused_token_after_rotation(auth_client):
    register_response = await auth_client.post(
        "/auth/register",
        json={"email": "refresh-reuse@example.com", "password": VALID_PASSWORD},
    )
    assert register_response.status_code == 201

    old_refresh = register_response.cookies[REFRESH_TOKEN_COOKIE]
    first_refresh = await auth_client.post(
        "/auth/refresh",
        cookies={REFRESH_TOKEN_COOKIE: old_refresh},
    )
    assert first_refresh.status_code == 200

    reuse_response = await auth_client.post(
        "/auth/refresh",
        cookies={REFRESH_TOKEN_COOKIE: old_refresh},
    )
    assert reuse_response.status_code == 401
    assert "invalid or expired" in reuse_response.json()["error"].lower()


@pytest.mark.asyncio
async def test_refresh_after_logout_returns_401(auth_client):
    register_response = await auth_client.post(
        "/auth/register",
        json={"email": "refresh-logout@example.com", "password": VALID_PASSWORD},
    )
    cookies = register_response.cookies

    logout_response = await auth_client.post("/auth/logout", cookies=cookies)
    assert logout_response.status_code == 200

    refresh_response = await auth_client.post(
        "/auth/refresh",
        cookies={REFRESH_TOKEN_COOKIE: cookies[REFRESH_TOKEN_COOKIE]},
    )
    assert refresh_response.status_code == 401
    assert "invalid or expired" in refresh_response.json()["error"].lower()


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(auth_client):
    response = await auth_client.post("/auth/refresh")
    assert response.status_code == 401
    assert "refresh token is required" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_protected_route_rejects_expired_access_token(auth_client, monkeypatch):
    monkeypatch.setenv("JWT_EXPIRES_IN", "1ms")
    get_settings.cache_clear()

    register_response = await auth_client.post(
        "/auth/register",
        json={"email": "expired-token@example.com", "password": VALID_PASSWORD},
    )
    token = register_response.json()["data"]["accessToken"]

    time.sleep(0.02)

    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_protected_route_rejects_token_for_deleted_user(auth_client, mongo_database):
    register_response = await auth_client.post(
        "/auth/register",
        json={"email": "deleted-user@example.com", "password": VALID_PASSWORD},
    )
    token = register_response.json()["data"]["accessToken"]
    user_id = register_response.json()["data"]["user"]["id"]

    await mongo_database["users"].delete_one({"_id": ObjectId(user_id)})

    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_malformed_bearer_header(auth_client):
    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": "NotBearer token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_rejects_invalid_email_format(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": VALID_PASSWORD},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_rejects_unknown_email_without_leaking_existence(auth_client):
    response = await auth_client.post(
        "/auth/login",
        json={"email": "ghost-user@example.com", "password": VALID_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_me_rejects_syntactically_valid_token_for_missing_user(auth_client):
    token = create_access_token(
        user_id="507f1f77bcf86cd799439011",
        email="orphan@example.com",
    )
    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
