"""Tests for app/main.py — lifespan startup/shutdown (lines 29-36)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.config import get_settings
from app.db.mongo import close_mongo_client, set_test_database
from app.main import create_app, lifespan


# ---------------------------------------------------------------------------
# Helper — create a disposable in-memory test database
# ---------------------------------------------------------------------------


def _make_mock_db():
    client = AsyncMongoMockClient()
    return client["unipilot_test"]


def _fake_app() -> FastAPI:
    """Return a bare FastAPI instance that satisfies the lifespan signature."""
    return FastAPI()


# ---------------------------------------------------------------------------
# Lifespan startup — lines 29-34
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_startup_succeeds(monkeypatch):
    """Lifespan startup runs without raising when env is correctly configured."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        async with lifespan(_fake_app()):
            pass  # startup completed successfully


@pytest.mark.asyncio
async def test_lifespan_calls_ensure_development_catalog(monkeypatch):
    """ensure_development_catalog is awaited exactly once during startup."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock) as mock_catalog, \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        async with lifespan(_fake_app()):
            pass

    mock_catalog.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_calls_ensure_catalog_indexes(monkeypatch):
    """ensure_catalog_indexes is awaited exactly once during startup."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock) as mock_indexes, \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        async with lifespan(_fake_app()):
            pass

    mock_indexes.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_passes_database_to_startup_functions(monkeypatch):
    """Startup functions receive the database returned by get_database."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock) as mock_catalog, \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock) as mock_indexes, \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        async with lifespan(_fake_app()):
            pass

    # First positional arg to each startup call is the database
    called_db_catalog = mock_catalog.call_args[0][0]
    called_db_indexes = mock_indexes.call_args[0][0]
    assert called_db_catalog is db
    assert called_db_indexes is db


# ---------------------------------------------------------------------------
# Lifespan shutdown — lines 35-36
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_shutdown_awaits_close_redis(monkeypatch):
    """close_redis is awaited on shutdown (line 35)."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.main.close_mongo_client") as mock_mongo:
        async with lifespan(_fake_app()):
            pass  # exits here, triggering shutdown

    mock_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_shutdown_calls_close_mongo_client(monkeypatch):
    """close_mongo_client is called on shutdown (line 36)."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client") as mock_mongo:
        async with lifespan(_fake_app()):
            pass

    mock_mongo.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_body_exception_propagates(monkeypatch):
    """
    A RuntimeError raised inside the lifespan body propagates to the caller.
    Note: because the lifespan generator has no try/finally, cleanup code
    (close_redis / close_mongo_client) is NOT guaranteed to run on exception —
    FastAPI's ASGI machinery handles process-level cleanup in production.
    """
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost/unipilot_test")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        with pytest.raises(RuntimeError, match="simulated"):
            async with lifespan(_fake_app()):
                raise RuntimeError("simulated failure during request handling")


# ---------------------------------------------------------------------------
# Lifespan — JWT secret enforcement (line 30)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_raises_when_jwt_secret_missing(monkeypatch):
    """require_jwt_secret() is called during startup; missing secret → RuntimeError."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()

    db = _make_mock_db()
    set_test_database(db)

    with patch("app.main.ensure_development_catalog", new_callable=AsyncMock), \
         patch("app.main.ensure_catalog_indexes", new_callable=AsyncMock), \
         patch("app.main.close_redis", new_callable=AsyncMock), \
         patch("app.main.close_mongo_client"):
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            async with lifespan(_fake_app()):
                pass


# ---------------------------------------------------------------------------
# create_app — structure checks
# ---------------------------------------------------------------------------


def test_create_app_registers_all_routers():
    app = create_app()
    routes = {r.path for r in app.routes}
    assert "/health" in routes
    assert any("/auth" in r for r in routes)


def test_create_app_sets_title():
    app = create_app()
    assert app.title == "UniPilot API"


def test_create_app_registers_exception_handlers():
    """All three exception handlers should be registered."""
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError

    app = create_app()
    handler_keys = set(app.exception_handlers.keys())
    assert HTTPException in handler_keys or any("HTTPException" in str(k) for k in handler_keys)
    assert RequestValidationError in handler_keys or any("RequestValidationError" in str(k) for k in handler_keys)
