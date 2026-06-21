"""Unit tests for app/db/redis_client.py — targets 100% branch coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.db.redis_client as rc_module
from app.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**kwargs) -> Settings:
    """Return a Settings instance with sensible test defaults."""
    defaults = dict(environment="development", jwt_secret="test-secret")
    defaults.update(kwargs)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# get_redis_client
# ---------------------------------------------------------------------------


def test_get_redis_client_returns_none_in_test_environment(monkeypatch) -> None:
    monkeypatch.setattr(rc_module, "_redis_client", None)
    monkeypatch.setattr(
        "app.db.redis_client.get_settings",
        lambda: _settings(environment="test", redis_url="redis://localhost"),
    )
    result = rc_module.get_redis_client()
    assert result is None


def test_get_redis_client_returns_none_when_no_redis_url(monkeypatch) -> None:
    monkeypatch.setattr(rc_module, "_redis_client", None)
    monkeypatch.setattr(
        "app.db.redis_client.get_settings",
        lambda: _settings(environment="development", redis_url=None),
    )
    result = rc_module.get_redis_client()
    assert result is None


def test_get_redis_client_creates_client_when_url_present(monkeypatch) -> None:
    monkeypatch.setattr(rc_module, "_redis_client", None)
    monkeypatch.setattr(
        "app.db.redis_client.get_settings",
        lambda: _settings(environment="development", redis_url="redis://localhost:6379"),
    )
    fake_client = MagicMock()
    with patch("app.db.redis_client.redis.from_url", return_value=fake_client) as mock_from_url:
        result = rc_module.get_redis_client()

    mock_from_url.assert_called_once_with(
        "redis://localhost:6379",
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    assert result is fake_client
    # Cleanup module-level singleton
    rc_module._redis_client = None


def test_get_redis_client_reuses_existing_singleton(monkeypatch) -> None:
    """Second call must NOT create a new client — returns the cached instance."""
    existing_client = MagicMock()
    monkeypatch.setattr(rc_module, "_redis_client", existing_client)
    monkeypatch.setattr(
        "app.db.redis_client.get_settings",
        lambda: _settings(environment="development", redis_url="redis://localhost:6379"),
    )
    with patch("app.db.redis_client.redis.from_url") as mock_from_url:
        result = rc_module.get_redis_client()

    mock_from_url.assert_not_called()
    assert result is existing_client
    # Cleanup
    rc_module._redis_client = None


# ---------------------------------------------------------------------------
# close_redis_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_redis_client_does_nothing_when_none(monkeypatch) -> None:
    monkeypatch.setattr(rc_module, "_redis_client", None)
    # Should complete without raising
    await rc_module.close_redis_client()
    assert rc_module._redis_client is None


@pytest.mark.asyncio
async def test_close_redis_client_closes_and_clears_singleton(monkeypatch) -> None:
    fake_client = AsyncMock()
    monkeypatch.setattr(rc_module, "_redis_client", fake_client)
    await rc_module.close_redis_client()
    fake_client.aclose.assert_awaited_once()
    assert rc_module._redis_client is None


# ---------------------------------------------------------------------------
# check_redis_connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_redis_connectivity_returns_not_configured_when_no_client(monkeypatch) -> None:
    monkeypatch.setattr(rc_module, "get_redis_client", lambda: None)
    result = await rc_module.check_redis_connectivity()
    assert result == "not_configured"


@pytest.mark.asyncio
async def test_check_redis_connectivity_returns_connected_on_successful_ping(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(rc_module, "get_redis_client", lambda: fake_client)
    result = await rc_module.check_redis_connectivity()
    assert result == "connected"
    fake_client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_connectivity_returns_disconnected_on_ping_failure(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
    monkeypatch.setattr(rc_module, "get_redis_client", lambda: fake_client)
    result = await rc_module.check_redis_connectivity()
    assert result == "disconnected"
