"""Unit tests for app/db/redis.py and app/db/redis_client.py wrappers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.redis import check_redis_connectivity, close_redis
from app.db.redis_client import (
    check_redis_connectivity as _check_pool_connectivity,
    close_redis_client,
    get_redis_client,
)


# ---------------------------------------------------------------------------
# redis_client — get_redis_client
# ---------------------------------------------------------------------------


def test_get_redis_client_returns_none_in_test_env(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    get_settings.cache_clear()

    # Import after env is patched
    import app.db.redis_client as rc
    rc._redis_client = None  # ensure clean state

    result = get_redis_client()
    assert result is None

    get_settings.cache_clear()


def test_get_redis_client_returns_none_when_no_url(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    import app.db.redis_client as rc
    rc._redis_client = None

    result = get_redis_client()
    assert result is None

    get_settings.cache_clear()


def test_get_redis_client_creates_client_when_url_set(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    get_settings.cache_clear()

    import app.db.redis_client as rc
    rc._redis_client = None

    with patch("app.db.redis_client.redis") as mock_redis_module:
        mock_client = MagicMock()
        mock_redis_module.from_url.return_value = mock_client
        result = get_redis_client()

    assert result is mock_client
    rc._redis_client = None
    get_settings.cache_clear()


def test_get_redis_client_returns_singleton(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    get_settings.cache_clear()

    import app.db.redis_client as rc
    rc._redis_client = None

    with patch("app.db.redis_client.redis") as mock_redis_module:
        mock_client = MagicMock()
        mock_redis_module.from_url.return_value = mock_client
        client1 = get_redis_client()
        client2 = get_redis_client()

    assert client1 is client2
    mock_redis_module.from_url.assert_called_once()
    rc._redis_client = None
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# redis_client — close_redis_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_redis_client_noop_when_none():
    import app.db.redis_client as rc
    rc._redis_client = None
    await close_redis_client()  # must not raise


@pytest.mark.asyncio
async def test_close_redis_client_closes_and_clears():
    import app.db.redis_client as rc
    mock_client = AsyncMock()
    rc._redis_client = mock_client

    await close_redis_client()

    mock_client.aclose.assert_awaited_once()
    assert rc._redis_client is None


# ---------------------------------------------------------------------------
# redis_client — check_redis_connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_pool_connectivity_returns_not_configured_when_client_none(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    import app.db.redis_client as rc
    rc._redis_client = None

    result = await _check_pool_connectivity()
    assert result == "not_configured"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_check_pool_connectivity_returns_connected_on_ping(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    get_settings.cache_clear()

    import app.db.redis_client as rc
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    rc._redis_client = mock_client

    result = await _check_pool_connectivity()
    assert result == "connected"

    rc._redis_client = None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_check_pool_connectivity_returns_disconnected_on_error(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    get_settings.cache_clear()

    import app.db.redis_client as rc
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=Exception("connection refused"))
    rc._redis_client = mock_client

    result = await _check_pool_connectivity()
    assert result == "disconnected"

    rc._redis_client = None
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# redis.py — thin facade delegates correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_wrapper_check_delegates_to_pool():
    with patch(
        "app.db.redis._check_pool_connectivity",
        new_callable=AsyncMock,
        return_value="connected",
    ) as mock_fn:
        result = await check_redis_connectivity()

    mock_fn.assert_awaited_once()
    assert result == "connected"


@pytest.mark.asyncio
async def test_redis_wrapper_close_delegates_to_client():
    with patch(
        "app.db.redis.close_redis_client",
        new_callable=AsyncMock,
    ) as mock_fn:
        await close_redis()

    mock_fn.assert_awaited_once()
