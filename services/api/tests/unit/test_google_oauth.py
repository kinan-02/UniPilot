"""Unit tests for Google OAuth helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.security.google_oauth import (
    GoogleOAuthError,
    GoogleUserInfo,
    build_google_authorization_url,
    verify_google_id_token,
)


def test_build_google_authorization_url_requires_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(GoogleOAuthError):
        build_google_authorization_url(state="state-token")


def test_build_google_authorization_url_includes_state(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    url = build_google_authorization_url(state="state-token")
    assert "accounts.google.com" in url
    assert "state=state-token" in url
    assert "client_id=client-id" in url


@pytest.mark.asyncio
async def test_exchange_code_for_id_token_returns_id_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id_token": "signed-id-token"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    with patch("app.security.google_oauth.httpx.AsyncClient", return_value=FakeClient()):
        from app.security.google_oauth import exchange_code_for_id_token

        token = await exchange_code_for_id_token("auth-code")
        assert token == "signed-id-token"


def test_verify_google_id_token_maps_claims(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    from app.config import get_settings

    get_settings.cache_clear()

    with patch("app.security.google_oauth.jwt.decode") as decode_mock, patch(
        "app.security.google_oauth.PyJWKClient"
    ) as jwk_client_mock:
        jwk_client_mock.return_value.get_signing_key_from_jwt.return_value.key = "public-key"
        decode_mock.return_value = {
            "iss": "accounts.google.com",
            "sub": "google-123",
            "email": "User@Example.com",
            "email_verified": True,
        }

        profile = verify_google_id_token("id-token")

    assert profile == GoogleUserInfo(
        google_id="google-123",
        email="user@example.com",
        email_verified=True,
    )


def test_verify_google_id_token_rejects_invalid_issuer(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    from app.config import get_settings

    get_settings.cache_clear()

    with patch("app.security.google_oauth.jwt.decode") as decode_mock, patch(
        "app.security.google_oauth.PyJWKClient"
    ) as jwk_client_mock:
        jwk_client_mock.return_value.get_signing_key_from_jwt.return_value.key = "public-key"
        decode_mock.return_value = {
            "iss": "evil.example.com",
            "sub": "google-123",
            "email": "user@example.com",
            "email_verified": True,
        }

        with pytest.raises(GoogleOAuthError):
            verify_google_id_token("id-token")


def test_verify_google_id_token_requires_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(GoogleOAuthError, match="not configured"):
        verify_google_id_token("id-token")


def test_verify_google_id_token_requires_email_claim(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.security.google_oauth.jwt.decode") as decode_mock, patch(
        "app.security.google_oauth.PyJWKClient"
    ) as jwk_client_mock:
        jwk_client_mock.return_value.get_signing_key_from_jwt.return_value.key = "public-key"
        decode_mock.return_value = {
            "iss": "accounts.google.com",
            "sub": "google-123",
            "email": "",
            "email_verified": True,
        }
        with pytest.raises(GoogleOAuthError, match="email is missing"):
            verify_google_id_token("id-token")


@pytest.mark.asyncio
async def test_exchange_code_for_id_token_requires_configuration(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    from app.config import get_settings
    from app.security.google_oauth import exchange_code_for_id_token

    get_settings.cache_clear()
    with pytest.raises(GoogleOAuthError, match="not configured"):
        await exchange_code_for_id_token("auth-code")


@pytest.mark.asyncio
async def test_exchange_code_for_id_token_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    from app.config import get_settings
    from app.security.google_oauth import exchange_code_for_id_token

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 400

        @staticmethod
        def json():
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    with patch("app.security.google_oauth.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(GoogleOAuthError, match="token exchange failed"):
            await exchange_code_for_id_token("auth-code")


@pytest.mark.asyncio
async def test_exchange_code_for_id_token_requires_id_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    from app.config import get_settings
    from app.security.google_oauth import exchange_code_for_id_token

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    with patch("app.security.google_oauth.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(GoogleOAuthError, match="missing id_token"):
            await exchange_code_for_id_token("auth-code")
