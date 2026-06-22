"""Unit tests for the auth dependency layer."""

import pytest
import jwt as pyjwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import MagicMock

from app.config import get_settings
from app.dependencies.auth import (
    AuthContext,
    get_bearer_token,
    require_auth,
    resolve_access_token,
)
from app.security.cookies import ACCESS_TOKEN_COOKIE


@pytest.fixture(autouse=True)
def jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _request(cookies: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.cookies = cookies or {}
    return request


class TestGetBearerToken:
    def test_returns_credentials_for_valid_bearer(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="my-token")
        assert get_bearer_token(creds) == "my-token"

    def test_returns_none_when_credentials_is_none(self):
        assert get_bearer_token(None) is None

    def test_returns_none_for_non_bearer_scheme(self):
        creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="dXNlcjpwYXNz")
        assert get_bearer_token(creds) is None

    def test_scheme_matching_is_case_insensitive(self):
        creds = HTTPAuthorizationCredentials(scheme="bearer", credentials="my-token")
        assert get_bearer_token(creds) == "my-token"


class TestResolveAccessToken:
    def test_prefers_bearer_header_over_cookie(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="header-token")
        token = resolve_access_token(
            _request({ACCESS_TOKEN_COOKIE: "cookie-token"}),
            creds,
            "cookie-token",
        )
        assert token == "header-token"

    def test_falls_back_to_access_token_cookie(self):
        token = resolve_access_token(
            _request(),
            None,
            "cookie-token",
        )
        assert token == "cookie-token"


@pytest.mark.asyncio
async def test_require_auth_raises_401_when_no_token():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(request=_request(), credentials=None, access_token_cookie=None)
    assert exc_info.value.status_code == 401
    assert "required" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_raises_401_for_malformed_token():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(request=_request(), credentials=creds, access_token_cookie=None)
    assert exc_info.value.status_code == 401
    assert "invalid or expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_raises_401_for_token_missing_sub_claim():
    secret = "test-jwt-secret"
    token = pyjwt.encode(
        {"email": "user@example.com"},
        secret,
        algorithm="HS256",
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(request=_request(), credentials=creds, access_token_cookie=None)
    assert exc_info.value.status_code == 401
    assert "invalid or expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_raises_401_for_token_missing_email_claim():
    secret = "test-jwt-secret"
    token = pyjwt.encode(
        {"sub": "507f1f77bcf86cd799439011"},
        secret,
        algorithm="HS256",
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(request=_request(), credentials=creds, access_token_cookie=None)
    assert exc_info.value.status_code == 401
    assert "invalid or expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_returns_auth_context_for_valid_token():
    from app.security.jwt import create_access_token

    token = create_access_token(
        user_id="507f1f77bcf86cd799439011",
        email="user@example.com",
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    result = await require_auth(request=_request(), credentials=creds, access_token_cookie=None)
    assert isinstance(result, AuthContext)
    assert result.user_id == "507f1f77bcf86cd799439011"
    assert result.email == "user@example.com"
