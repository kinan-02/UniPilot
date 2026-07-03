import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db.mongo import set_test_database
from app.main import create_app
from app.routes.outlook_integration import reset_outlook_integration_indexes_state
from app.security.outlook_oauth_state import reset_in_memory_outlook_oauth_state_store


@pytest.fixture
async def outlook_client(mongo_database, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("JWT_EXPIRES_IN", "1h")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test-client-id")
    monkeypatch.setenv(
        "MICROSOFT_TOKEN_ENCRYPTION_KEY",
        "test-outlook-token-encryption-key-32chars",
    )
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


async def _register_and_login(client: AsyncClient) -> str:
    await client.post(
        "/auth/register",
        json={"email": "outlook@test.com", "password": "Password1!"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "outlook@test.com", "password": "Password1!"},
    )
    return login.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_outlook_status_not_connected(outlook_client):
    token = await _register_and_login(outlook_client)
    response = await outlook_client.get(
        "/integrations/outlook/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["connected"] is False
    assert response.json()["data"]["available"] is True


@pytest.mark.asyncio
async def test_outlook_connect_redirects_when_configured(outlook_client):
    token = await _register_and_login(outlook_client)
    response = await outlook_client.get(
        "/integrations/outlook/connect",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "login.microsoftonline.com" in location
    assert "code_challenge=" in location


@pytest.mark.asyncio
async def test_outlook_disconnect_is_idempotent(outlook_client):
    token = await _register_and_login(outlook_client)
    response = await outlook_client.delete(
        "/integrations/outlook/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["disconnected"] is False
