import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db.mongo import set_test_database
from app.main import create_app
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
async def test_outlook_callback_invalid_state_redirects(outlook_callback_client):
    response = await outlook_callback_client.get(
        "/integrations/outlook/callback",
        params={"code": "abc", "state": "missing-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "code=outlook_invalid_state" in response.headers["location"]


@pytest.mark.asyncio
async def test_outlook_callback_denied_redirects(outlook_callback_client):
    response = await outlook_callback_client.get(
        "/integrations/outlook/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "code=outlook_denied" in response.headers["location"]


@pytest.mark.asyncio
async def test_outlook_connect_unconfigured_returns_503(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_TOKEN_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    set_test_database(mongo_database)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "nocfg@test.com", "password": "Password1!"},
        )
        login = await client.post(
            "/auth/login",
            json={"email": "nocfg@test.com", "password": "Password1!"},
        )
        token = login.json()["data"]["accessToken"]
        response = await client.get(
            "/integrations/outlook/connect",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
        assert response.status_code == 503

    set_test_database(None)


@pytest.mark.asyncio
async def test_outlook_callback_not_configured(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_TOKEN_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/integrations/outlook/callback",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "code=outlook_not_configured" in response.headers["location"]
