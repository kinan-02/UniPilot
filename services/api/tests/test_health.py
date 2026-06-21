import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.routes.health import resolve_service_status


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health_returns_service_payload_without_dependencies(app, monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "api"
    assert body["status"] == "ok"
    assert body["environment"] == "development"
    assert isinstance(body["timestamp"], str)
    assert body["dependencies"]["mongo"] == "not_configured"
    assert body["dependencies"]["redis"] == "not_configured"


@pytest.mark.asyncio
async def test_health_reports_degraded_when_mongo_is_configured_but_unreachable(app, monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://invalid:27017/unipilot_python?authSource=admin")
    monkeypatch.delenv("REDIS_URL", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["dependencies"]["mongo"] == "disconnected"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_uses_environment_name_from_env(app, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["environment"] == "test"


class TestResolveServiceStatus:
    def test_returns_ok_when_both_not_configured(self):
        assert resolve_service_status("not_configured", "not_configured") == "ok"

    def test_returns_ok_when_both_connected(self):
        assert resolve_service_status("ok", "ok") == "ok"

    def test_returns_ok_when_mongo_connected_redis_not_configured(self):
        assert resolve_service_status("ok", "not_configured") == "ok"

    def test_returns_ok_when_redis_connected_mongo_not_configured(self):
        assert resolve_service_status("not_configured", "ok") == "ok"

    def test_returns_degraded_when_mongo_disconnected(self):
        assert resolve_service_status("disconnected", "ok") == "degraded"

    def test_returns_degraded_when_redis_disconnected(self):
        assert resolve_service_status("ok", "disconnected") == "degraded"

    def test_returns_degraded_when_both_disconnected(self):
        assert resolve_service_status("disconnected", "disconnected") == "degraded"

    def test_returns_degraded_when_mongo_disconnected_redis_not_configured(self):
        assert resolve_service_status("disconnected", "not_configured") == "degraded"
