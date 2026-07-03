import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db.mongo import set_test_database
from app.main import create_app
from app.repositories.outlook_token_repository import find_outlook_tokens_by_user_id
from app.routes.outlook_integration import reset_outlook_integration_indexes_state
from app.security.outlook_oauth_state import (
    issue_outlook_oauth_state,
    reset_in_memory_outlook_oauth_state_store,
)


@pytest.fixture
async def outlook_callback_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test-client-id")
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
    monkeypatch.setenv("WEB_APP_URL", "http://localhost:3000")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)
    reset_outlook_integration_indexes_state()
    reset_in_memory_outlook_oauth_state_store()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    set_test_database(None)
    reset_outlook_integration_indexes_state()
    reset_in_memory_outlook_oauth_state_store()


@pytest.mark.asyncio
async def test_outlook_callback_success_stores_tokens(outlook_callback_client, mongo_database):
    user_id = "507f1f77bcf86cd799439011"
    state = await issue_outlook_oauth_state(user_id=user_id, code_verifier="verifier")

    with respx.mock:
        respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "Mail.Read",
                    "token_type": "Bearer",
                },
            )
        )
        respx.get("https://graph.microsoft.com/v1.0/me").mock(
            return_value=httpx.Response(
                200,
                json={"id": "ms-user", "mail": "user@example.com", "displayName": "User"},
            )
        )

        response = await outlook_callback_client.get(
            "/integrations/outlook/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "outlook=connected" in response.headers["location"]

    stored = await find_outlook_tokens_by_user_id(mongo_database, user_id)
    assert stored is not None
    assert stored["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_outlook_callback_missing_code_redirects(outlook_callback_client):
    response = await outlook_callback_client.get(
        "/integrations/outlook/callback",
        params={"state": "some-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "code=outlook_invalid_callback" in response.headers["location"]


@pytest.mark.asyncio
async def test_outlook_callback_missing_refresh_token(outlook_callback_client):
    user_id = "507f1f77bcf86cd799439011"
    state = await issue_outlook_oauth_state(user_id=user_id, code_verifier="verifier")

    with respx.mock:
        respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "expires_in": 3600,
                    "scope": "Mail.Read",
                    "token_type": "Bearer",
                },
            )
        )

        response = await outlook_callback_client.get(
            "/integrations/outlook/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "code=outlook_missing_refresh_token" in response.headers["location"]


@pytest.mark.asyncio
async def test_outlook_callback_auth_failed(outlook_callback_client):
    user_id = "507f1f77bcf86cd799439011"
    state = await issue_outlook_oauth_state(user_id=user_id, code_verifier="verifier")

    with respx.mock:
        respx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )

        response = await outlook_callback_client.get(
            "/integrations/outlook/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "code=outlook_auth_failed" in response.headers["location"]


@pytest.mark.asyncio
async def test_outlook_status_skips_index_setup_when_ready(outlook_callback_client, monkeypatch):
    await outlook_callback_client.post(
        "/auth/register",
        json={"email": "idx@test.com", "password": "Password1!"},
    )
    login = await outlook_callback_client.post(
        "/auth/login",
        json={"email": "idx@test.com", "password": "Password1!"},
    )
    token = login.json()["data"]["accessToken"]

    first = await outlook_callback_client.get(
        "/integrations/outlook/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await outlook_callback_client.get(
        "/integrations/outlook/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
