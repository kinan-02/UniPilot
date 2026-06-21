"""Unit tests for the auth dependency layer."""

import pytest
import jwt as pyjwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import get_settings
from app.dependencies.auth import AuthContext, get_bearer_token, require_auth


@pytest.fixture(autouse=True)
def jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


@pytest.mark.asyncio
async def test_require_auth_raises_401_when_no_token():
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(credentials=None)
    assert exc_info.value.status_code == 401
    assert "required" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_raises_401_for_malformed_token():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(credentials=creds)
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
        await require_auth(credentials=creds)
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
        await require_auth(credentials=creds)
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
    result = await require_auth(credentials=creds)
    assert isinstance(result, AuthContext)
    assert result.user_id == "507f1f77bcf86cd799439011"
    assert result.email == "user@example.com"
