"""Unit tests for auth cookies and refresh token rotation."""

from __future__ import annotations

import pytest
from fastapi import Response
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db.mongo import set_test_database
from app.main import create_app
from app.security.cookies import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.security.refresh_tokens import (
    issue_refresh_token,
    reset_in_memory_refresh_token_store,
    rotate_refresh_token,
)


@pytest.mark.asyncio
async def test_register_sets_http_only_auth_cookies(security_client):
    response = await security_client.post(
        "/auth/register",
        json={"email": "cookie-user@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 201
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header for header in set_cookie_headers)
    assert any("HttpOnly" in header for header in set_cookie_headers)
    assert any(REFRESH_TOKEN_COOKIE in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_me_accepts_access_token_cookie(security_client):
    register_response = await security_client.post(
        "/auth/register",
        json={"email": "cookie-me@example.com", "password": "StrongPass123!"},
    )
    cookies = {
        ACCESS_TOKEN_COOKIE: register_response.cookies[ACCESS_TOKEN_COOKIE],
    }

    response = await security_client.get("/auth/me", cookies=cookies)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "cookie-me@example.com"


@pytest.mark.asyncio
async def test_refresh_rotates_session(security_client):
    register_response = await security_client.post(
        "/auth/register",
        json={"email": "refresh-user@example.com", "password": "StrongPass123!"},
    )
    cookies = {
        REFRESH_TOKEN_COOKIE: register_response.cookies[REFRESH_TOKEN_COOKIE],
    }

    refresh_response = await security_client.post("/auth/refresh", cookies=cookies)
    assert refresh_response.status_code == 200
    assert refresh_response.cookies[ACCESS_TOKEN_COOKIE]
    assert refresh_response.cookies[REFRESH_TOKEN_COOKIE]


@pytest.mark.asyncio
async def test_logout_clears_auth_cookies(security_client):
    register_response = await security_client.post(
        "/auth/register",
        json={"email": "logout-user@example.com", "password": "StrongPass123!"},
    )
    cookies = register_response.cookies

    logout_response = await security_client.post("/auth/logout", cookies=cookies)
    assert logout_response.status_code == 200
    cleared = logout_response.headers.get_list("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header and "Max-Age=0" in header for header in cleared)


def test_set_and_clear_auth_cookies() -> None:
    response = Response()
    set_auth_cookies(response, access_token="access", refresh_token="refresh")
    headers = response.headers.getlist("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header for header in headers)

    clear_auth_cookies(response)
    cleared = response.headers.getlist("set-cookie")
    assert any(ACCESS_TOKEN_COOKIE in header for header in cleared)


@pytest.mark.asyncio
async def test_refresh_token_rotation_consumes_old_token() -> None:
    reset_in_memory_refresh_token_store()
    token = await issue_refresh_token(user_id="user-1")
    rotation = await rotate_refresh_token(token)
    assert rotation is not None
    assert rotation[0] == "user-1"
    assert await rotate_refresh_token(token) is None


@pytest.mark.asyncio
async def test_openapi_is_disabled_in_production(monkeypatch, mongo_database):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("MONGO_ROOT_PASSWORD", "strong-production-mongo-password")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "y" * 32)
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("AI_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 404
