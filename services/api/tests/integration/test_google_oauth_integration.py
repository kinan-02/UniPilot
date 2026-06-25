"""Tests for Google OAuth and remember-me auth flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from app.security.google_oauth import GoogleOAuthError, GoogleUserInfo
from app.security.oauth_state import issue_oauth_state

VALID_PASSWORD = "StrongPass123!"


def _enable_google_oauth(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-client-secret")
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_providers_reports_google_disabled_by_default(auth_client):
    response = await auth_client.get("/auth/providers")
    assert response.status_code == 200
    assert response.json()["data"]["google"] is False


@pytest.mark.asyncio
async def test_google_start_returns_503_when_not_configured(auth_client):
    response = await auth_client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_google_callback_redirects_when_not_configured(auth_client):
    response = await auth_client.get("/auth/google/callback", follow_redirects=False)
    assert response.status_code == 302
    assert "error=google_not_configured" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_handles_provider_error(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    response = await auth_client.get(
        "/auth/google/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=google_denied" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_requires_code_and_state(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    response = await auth_client.get("/auth/google/callback", follow_redirects=False)
    assert response.status_code == 302
    assert "error=google_invalid_callback" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_rejects_invalid_state(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    response = await auth_client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": "invalid"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=google_invalid_state" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_handles_token_exchange_failure(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    state = await issue_oauth_state(remember_me=False)
    with patch(
        "app.routes.auth.exchange_code_for_id_token",
        new=AsyncMock(side_effect=GoogleOAuthError("failed")),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "error=google_auth_failed" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_rejects_unverified_email(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    state = await issue_oauth_state(remember_me=False)
    google_user = GoogleUserInfo(
        google_id="google-sub-unverified",
        email="unverified@example.com",
        email_verified=False,
    )
    with (
        patch("app.routes.auth.exchange_code_for_id_token", new=AsyncMock(return_value="id-token")),
        patch("app.routes.auth.verify_google_id_token", return_value=google_user),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "error=google_email_unverified" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_recovers_from_duplicate_key_race(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    monkeypatch.setenv("WEB_APP_URL", "http://testserver")
    from app.config import get_settings

    get_settings.cache_clear()

    state = await issue_oauth_state(remember_me=True)
    google_user = GoogleUserInfo(
        google_id="google-sub-race",
        email="race-user@example.com",
        email_verified=True,
    )
    created_user = {
        "_id": "665f2b0f2a3f7b2a1a9a7fff",
        "email": "race-user@example.com",
        "authProvider": "google",
        "googleId": "google-sub-race",
        "createdAt": "2025-01-01T00:00:00Z",
    }

    with (
        patch("app.routes.auth.exchange_code_for_id_token", new=AsyncMock(return_value="id-token")),
        patch("app.routes.auth.verify_google_id_token", return_value=google_user),
        patch("app.routes.auth.find_user_by_google_id", new=AsyncMock(side_effect=[None, created_user])),
        patch("app.routes.auth.find_user_by_email", new=AsyncMock(return_value=None)),
        patch(
            "app.routes.auth.create_google_user",
            new=AsyncMock(side_effect=DuplicateKeyError("duplicate")),
        ),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "http://testserver/auth/callback"


@pytest.mark.asyncio
async def test_providers_reports_google_enabled_when_configured(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)

    response = await auth_client.get("/auth/providers")
    assert response.status_code == 200
    assert response.json()["data"]["google"] is True


@pytest.mark.asyncio
async def test_login_rejects_google_only_account(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "google-only@example.com", "password": VALID_PASSWORD},
    )

    from app.db.mongo import get_database

    db = await get_database()
    await db.users.update_one(
        {"email": "google-only@example.com"},
        {"$unset": {"passwordHash": ""}, "$set": {"authProvider": "google"}},
    )

    response = await auth_client.post(
        "/auth/login",
        json={"email": "google-only@example.com", "password": VALID_PASSWORD},
    )
    assert response.status_code == 401
    assert "Google" in response.json()["error"]


@pytest.mark.asyncio
async def test_login_remember_me_sets_persistent_refresh_cookie(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "remember@example.com", "password": VALID_PASSWORD},
    )

    response = await auth_client.post(
        "/auth/login",
        json={
            "email": "remember@example.com",
            "password": VALID_PASSWORD,
            "rememberMe": True,
        },
    )
    assert response.status_code == 200
    refresh_cookie = next(
        header
        for header in response.headers.get_list("set-cookie")
        if "unipilot_refresh_token" in header
    )
    assert "Max-Age=" in refresh_cookie


@pytest.mark.asyncio
async def test_login_without_remember_me_uses_session_refresh_cookie(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "session@example.com", "password": VALID_PASSWORD},
    )

    response = await auth_client.post(
        "/auth/login",
        json={
            "email": "session@example.com",
            "password": VALID_PASSWORD,
            "rememberMe": False,
        },
    )
    assert response.status_code == 200
    refresh_cookie = next(
        header
        for header in response.headers.get_list("set-cookie")
        if "unipilot_refresh_token" in header
    )
    assert "Max-Age=" not in refresh_cookie


@pytest.mark.asyncio
async def test_google_start_redirects_when_configured(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)

    response = await auth_client.get(
        "/auth/google",
        params={"rememberMe": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_creates_user_and_sets_cookies(auth_client, monkeypatch):
    _enable_google_oauth(monkeypatch)
    monkeypatch.setenv("WEB_APP_URL", "http://testserver")
    from app.config import get_settings

    get_settings.cache_clear()

    state = await issue_oauth_state(remember_me=True)
    google_user = GoogleUserInfo(
        google_id="google-sub-123",
        email="oauth-user@example.com",
        email_verified=True,
    )

    with (
        patch(
            "app.routes.auth.exchange_code_for_id_token",
            new=AsyncMock(return_value="id-token"),
        ),
        patch(
            "app.routes.auth.verify_google_id_token",
            return_value=google_user,
        ),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "http://testserver/auth/callback"
    assert any("unipilot_access_token" in header for header in response.headers.get_list("set-cookie"))

    me_response = await auth_client.get("/auth/me", cookies=response.cookies)
    assert me_response.status_code == 200
    assert me_response.json()["data"]["user"]["email"] == "oauth-user@example.com"
    assert me_response.json()["data"]["user"]["authProvider"] == "google"


@pytest.mark.asyncio
async def test_google_callback_rejects_existing_local_account(auth_client, monkeypatch):
    await auth_client.post(
        "/auth/register",
        json={"email": "local-user@example.com", "password": VALID_PASSWORD},
    )

    _enable_google_oauth(monkeypatch)
    monkeypatch.setenv("WEB_APP_URL", "http://testserver")
    from app.config import get_settings

    get_settings.cache_clear()

    state = await issue_oauth_state(remember_me=False)
    google_user = GoogleUserInfo(
        google_id="google-sub-456",
        email="local-user@example.com",
        email_verified=True,
    )

    with (
        patch(
            "app.routes.auth.exchange_code_for_id_token",
            new=AsyncMock(return_value="id-token"),
        ),
        patch(
            "app.routes.auth.verify_google_id_token",
            return_value=google_user,
        ),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "error=google_account_exists" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_returns_account_exists_when_duplicate_has_no_user(
    auth_client,
    monkeypatch,
):
    _enable_google_oauth(monkeypatch)
    monkeypatch.setenv("WEB_APP_URL", "http://testserver")
    from app.config import get_settings

    get_settings.cache_clear()

    state = await issue_oauth_state(remember_me=False)
    google_user = GoogleUserInfo(
        google_id="google-sub-missing",
        email="missing-user@example.com",
        email_verified=True,
    )

    with (
        patch("app.routes.auth.exchange_code_for_id_token", new=AsyncMock(return_value="id-token")),
        patch("app.routes.auth.verify_google_id_token", return_value=google_user),
        patch("app.routes.auth.find_user_by_google_id", new=AsyncMock(side_effect=[None, None])),
        patch("app.routes.auth.find_user_by_email", new=AsyncMock(return_value=None)),
        patch(
            "app.routes.auth.create_google_user",
            new=AsyncMock(side_effect=DuplicateKeyError("duplicate")),
        ),
    ):
        response = await auth_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "error=google_account_exists" in response.headers["location"]


def _enable_e2e_google_stub(monkeypatch) -> None:
    _enable_google_oauth(monkeypatch)
    monkeypatch.setenv("E2E_GOOGLE_OAUTH_STUB", "true")


@pytest.mark.asyncio
async def test_google_callback_accepts_e2e_stub_code(auth_client, monkeypatch):
    _enable_e2e_google_stub(monkeypatch)
    monkeypatch.setenv("WEB_APP_URL", "http://testserver")

    state = await issue_oauth_state(remember_me=False)
    response = await auth_client.get(
        "/auth/google/callback",
        params={
            "code": "e2e|stub-oauth-user@example.com|google-sub-stub",
            "state": state,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].endswith("/auth/callback")

    me_response = await auth_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["data"]["user"]["email"] == "stub-oauth-user@example.com"
    assert me_response.json()["data"]["user"]["authProvider"] == "google"


@pytest.mark.asyncio
async def test_google_callback_rejects_malformed_e2e_stub_code(auth_client, monkeypatch):
    _enable_e2e_google_stub(monkeypatch)

    state = await issue_oauth_state(remember_me=False)
    response = await auth_client.get(
        "/auth/google/callback",
        params={"code": "e2e|missing-google-id", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "error=google_auth_failed" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_rejects_blank_e2e_stub_identity(auth_client, monkeypatch):
    _enable_e2e_google_stub(monkeypatch)

    state = await issue_oauth_state(remember_me=False)
    response = await auth_client.get(
        "/auth/google/callback",
        params={"code": "e2e|   |   ", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "error=google_auth_failed" in response.headers["location"]
