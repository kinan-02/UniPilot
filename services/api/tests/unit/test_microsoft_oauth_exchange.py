import httpx
import pytest
import respx

from app.config import get_settings
from app.security.microsoft_oauth import (
    MicrosoftOAuthError,
    exchange_code_for_tokens,
    fetch_microsoft_user_profile,
)


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_for_tokens(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
    get_settings.cache_clear()

    respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "scope": "Mail.Read",
                "token_type": "Bearer",
            },
        )
    )

    token_response = await exchange_code_for_tokens(code="code", code_verifier="verifier")
    assert token_response.access_token == "access"
    assert token_response.refresh_token == "refresh"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_microsoft_user_profile(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    get_settings.cache_clear()

    respx.get("https://graph.microsoft.com/v1.0/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "ms-user",
                "mail": "user@example.com",
                "displayName": "User",
            },
        )
    )

    profile = await fetch_microsoft_user_profile("access-token")
    assert profile.microsoft_user_id == "ms-user"
    assert profile.email == "user@example.com"


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_failure(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    get_settings.cache_clear()

    respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    with pytest.raises(MicrosoftOAuthError):
        await exchange_code_for_tokens(code="bad", code_verifier="verifier")


@pytest.mark.asyncio
async def test_exchange_code_requires_client_id(monkeypatch):
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    get_settings.cache_clear()
    with pytest.raises(MicrosoftOAuthError):
        await exchange_code_for_tokens(code="code", code_verifier="verifier")


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_missing_access_token(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    get_settings.cache_clear()

    respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
        return_value=httpx.Response(200, json={"refresh_token": "refresh"})
    )

    with pytest.raises(MicrosoftOAuthError):
        await exchange_code_for_tokens(code="code", code_verifier="verifier")
