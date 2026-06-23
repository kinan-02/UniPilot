"""Unit tests for app/middleware/auth_rate_limiter.py — targets 100% branch coverage."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.middleware.auth_rate_limiter as rl_module
from app.config import Settings, get_settings
from app.middleware.auth_rate_limiter import (
    AI_RATE_LIMIT_PREFIX,
    PROGRESS_RATE_LIMIT_PREFIX,
    RATE_LIMIT_PREFIX,
    InMemoryRateLimitStore,
    RedisRateLimitStore,
    _enforce_rate_limit,
    build_rate_limit_key,
    enforce_ai_rate_limit,
    enforce_auth_rate_limits,
    enforce_progress_rate_limit,
    reset_in_memory_rate_limit_store,
    resolve_rate_limit_store,
    set_rate_limit_store,
    build_email_rate_limit_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_request(host: str = "127.0.0.1", path: str = "/auth/login") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = host
    req.url = MagicMock()
    req.url.path = path
    return req


def _settings(**kwargs) -> Settings:
    defaults = dict(environment="development", jwt_secret="test-secret")
    defaults.update(kwargs)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# InMemoryRateLimitStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_store_allows_up_to_max_requests() -> None:
    store = InMemoryRateLimitStore()
    for _ in range(5):
        allowed = await store.is_allowed("key1", window_ms=60_000, max_requests=5)
        assert allowed is True


@pytest.mark.asyncio
async def test_in_memory_store_denies_request_exceeding_max() -> None:
    store = InMemoryRateLimitStore()
    for _ in range(3):
        await store.is_allowed("key1", window_ms=60_000, max_requests=3)

    result = await store.is_allowed("key1", window_ms=60_000, max_requests=3)
    assert result is False


@pytest.mark.asyncio
async def test_in_memory_store_respects_window_expiry() -> None:
    store = InMemoryRateLimitStore()
    # Manually inject an old timestamp outside the 100ms window
    old_ts = (time.time() - 1) * 1000  # 1 second ago
    store._hits["key"] = [old_ts, old_ts, old_ts]

    # With max=3 and window=100ms, those old hits should fall outside the window
    result = await store.is_allowed("key", window_ms=100, max_requests=3)
    assert result is True


def test_in_memory_store_reset_clears_all_hits() -> None:
    store = InMemoryRateLimitStore()
    store._hits["key"] = [1.0, 2.0]
    store.reset()
    assert len(store._hits) == 0


# ---------------------------------------------------------------------------
# RedisRateLimitStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_store_uses_in_memory_fallback_when_client_is_none(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: None)
    store = RedisRateLimitStore("redis://localhost")
    result = await store.is_allowed("key", window_ms=60_000, max_requests=10)
    assert result is True


@pytest.mark.asyncio
async def test_redis_store_sets_pexpire_on_first_hit(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.incr = AsyncMock(return_value=1)  # count == 1 → set expiry
    fake_client.pexpire = AsyncMock()
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: fake_client)

    store = RedisRateLimitStore("redis://localhost")
    result = await store.is_allowed("key", window_ms=5_000, max_requests=10)

    assert result is True
    fake_client.pexpire.assert_awaited_once_with("key", 5_000)


@pytest.mark.asyncio
async def test_redis_store_does_not_set_pexpire_on_subsequent_hits(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.incr = AsyncMock(return_value=5)  # count > 1
    fake_client.pexpire = AsyncMock()
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: fake_client)

    store = RedisRateLimitStore("redis://localhost")
    await store.is_allowed("key", window_ms=5_000, max_requests=10)

    fake_client.pexpire.assert_not_called()


@pytest.mark.asyncio
async def test_redis_store_returns_false_when_count_exceeds_max(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.incr = AsyncMock(return_value=11)  # count > max_requests=10
    fake_client.pexpire = AsyncMock()
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: fake_client)

    store = RedisRateLimitStore("redis://localhost")
    result = await store.is_allowed("key", window_ms=60_000, max_requests=10)

    assert result is False


@pytest.mark.asyncio
async def test_redis_store_uses_in_memory_fallback_on_redis_exception(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.incr = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: fake_client)
    reset_in_memory_rate_limit_store()

    store = RedisRateLimitStore("redis://localhost", fail_closed=True)
    result = await store.is_allowed("key", window_ms=60_000, max_requests=10)

    assert result is True


@pytest.mark.asyncio
async def test_redis_store_returns_false_when_fail_open_disabled(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.incr = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr(rl_module, "get_redis_client", lambda: fake_client)

    store = RedisRateLimitStore("redis://localhost", fail_closed=False)
    result = await store.is_allowed("key", window_ms=60_000, max_requests=10)

    assert result is False


# ---------------------------------------------------------------------------
# resolve_rate_limit_store
# ---------------------------------------------------------------------------


def test_resolve_returns_override_when_set(monkeypatch) -> None:
    fake_store = MagicMock()
    monkeypatch.setattr(rl_module, "_store_override", fake_store)
    result = resolve_rate_limit_store()
    assert result is fake_store
    # Cleanup
    monkeypatch.setattr(rl_module, "_store_override", None)


def test_resolve_returns_in_memory_store_in_test_env(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="test", redis_url=None),
    )
    result = resolve_rate_limit_store()
    assert isinstance(result, InMemoryRateLimitStore)


def test_resolve_returns_in_memory_store_when_no_redis_url(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="development", redis_url=None),
    )
    result = resolve_rate_limit_store()
    assert isinstance(result, InMemoryRateLimitStore)


def test_resolve_returns_redis_store_when_redis_url_present(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="development", redis_url="redis://localhost:6379"),
    )
    result = resolve_rate_limit_store()
    assert isinstance(result, RedisRateLimitStore)


# ---------------------------------------------------------------------------
# set_rate_limit_store / reset_in_memory_rate_limit_store
# ---------------------------------------------------------------------------


def test_set_rate_limit_store_updates_override(monkeypatch) -> None:
    fake_store = MagicMock()
    set_rate_limit_store(fake_store)
    assert rl_module._store_override is fake_store
    set_rate_limit_store(None)
    assert rl_module._store_override is None


def test_reset_in_memory_rate_limit_store_clears_hits() -> None:
    rl_module._in_memory_store._hits["x"] = [1.0]
    reset_in_memory_rate_limit_store()
    assert len(rl_module._in_memory_store._hits) == 0


# ---------------------------------------------------------------------------
# build_rate_limit_key
# ---------------------------------------------------------------------------


def test_build_rate_limit_key_uses_client_host_and_path() -> None:
    req = _fake_request(host="10.0.0.1", path="/auth/register")
    key = build_rate_limit_key(req)
    assert key == f"{RATE_LIMIT_PREFIX}ip:10.0.0.1:/auth/register"


def test_build_rate_limit_key_handles_missing_client() -> None:
    req = MagicMock()
    req.client = None
    req.url.path = "/auth/login"
    key = build_rate_limit_key(req)
    assert "unknown" in key


# ---------------------------------------------------------------------------
# _enforce_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_rate_limit_raises_429_when_not_allowed(monkeypatch) -> None:
    fake_store = AsyncMock()
    fake_store.is_allowed = AsyncMock(return_value=False)
    monkeypatch.setattr(rl_module, "resolve_rate_limit_store", lambda: fake_store)

    with pytest.raises(HTTPException) as exc_info:
        await _enforce_rate_limit(
            key="test-key",
            window_ms=60_000,
            max_requests=10,
            detail="Too many requests.",
        )

    assert exc_info.value.status_code == 429
    assert "Too many requests." in exc_info.value.detail


@pytest.mark.asyncio
async def test_enforce_rate_limit_passes_when_allowed(monkeypatch) -> None:
    fake_store = AsyncMock()
    fake_store.is_allowed = AsyncMock(return_value=True)
    monkeypatch.setattr(rl_module, "resolve_rate_limit_store", lambda: fake_store)

    # Should not raise
    await _enforce_rate_limit(
        key="test-key",
        window_ms=60_000,
        max_requests=10,
        detail="Too many requests.",
    )


# ---------------------------------------------------------------------------
# enforce_auth_rate_limits / enforce_ai_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_auth_rate_limits_passes_on_first_request(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="test", redis_url=None),
    )
    reset_in_memory_rate_limit_store()
    req = _fake_request()
    await enforce_auth_rate_limits(req, email="user@example.com")


@pytest.mark.asyncio
async def test_enforce_auth_rate_limits_raises_429_after_exceeding_max(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(
            environment="test",
            redis_url=None,
            auth_rate_limit_max=2,
            auth_rate_limit_window_ms=60_000,
        ),
    )
    reset_in_memory_rate_limit_store()
    req = _fake_request()

    await enforce_auth_rate_limits(req, email="user@example.com")
    await enforce_auth_rate_limits(req, email="user@example.com")

    with pytest.raises(HTTPException) as exc_info:
        await enforce_auth_rate_limits(req, email="user@example.com")
    assert exc_info.value.status_code == 429


def test_build_email_rate_limit_key_normalizes_email() -> None:
    key = build_email_rate_limit_key(email="User@Example.com", path="/auth/login")
    assert key == f"{RATE_LIMIT_PREFIX}email:user@example.com:/auth/login"


@pytest.mark.asyncio
async def test_enforce_ai_rate_limit_raises_429_after_exceeding_max(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(
            environment="test",
            redis_url=None,
            ai_rate_limit_max=1,
            ai_rate_limit_window_ms=60_000,
        ),
    )
    reset_in_memory_rate_limit_store()
    req = _fake_request(path="/ai/analyze")

    await enforce_ai_rate_limit(req, user_id="user_123")

    with pytest.raises(HTTPException) as exc_info:
        await enforce_ai_rate_limit(req, user_id="user_123")
    assert exc_info.value.status_code == 429
    assert "AI" in exc_info.value.detail


@pytest.mark.asyncio
async def test_enforce_ai_rate_limit_uses_user_id_in_key(monkeypatch) -> None:
    captured_keys: list[str] = []

    async def fake_enforce(*, key, window_ms, max_requests, detail):
        captured_keys.append(key)

    monkeypatch.setattr(rl_module, "_enforce_rate_limit", fake_enforce)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="test", redis_url=None),
    )

    req = _fake_request(path="/ai/plan")
    await enforce_ai_rate_limit(req, user_id="student_42")

    assert len(captured_keys) == 1
    assert "student_42" in captured_keys[0]
    assert captured_keys[0].startswith(AI_RATE_LIMIT_PREFIX)


@pytest.mark.asyncio
async def test_enforce_progress_rate_limit_raises_429_after_exceeding_max(monkeypatch) -> None:
    monkeypatch.setattr(rl_module, "_store_override", None)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(
            environment="test",
            redis_url=None,
            progress_rate_limit_max=1,
            progress_rate_limit_window_ms=60_000,
        ),
    )
    reset_in_memory_rate_limit_store()
    req = _fake_request(path="/graduation-progress")

    await enforce_progress_rate_limit(req, user_id="user_123")

    with pytest.raises(HTTPException) as exc_info:
        await enforce_progress_rate_limit(req, user_id="user_123")
    assert exc_info.value.status_code == 429
    assert "progress" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_enforce_progress_rate_limit_uses_user_id_in_key(monkeypatch) -> None:
    captured_keys: list[str] = []

    async def fake_enforce(*, key, window_ms, max_requests, detail):
        captured_keys.append(key)

    monkeypatch.setattr(rl_module, "_enforce_rate_limit", fake_enforce)
    monkeypatch.setattr(
        rl_module, "get_settings",
        lambda: _settings(environment="test", redis_url=None),
    )

    req = _fake_request(path="/graduation-progress/curriculum-graph")
    await enforce_progress_rate_limit(req, user_id="student_42")

    assert len(captured_keys) == 1
    assert captured_keys[0].startswith(f"{PROGRESS_RATE_LIMIT_PREFIX}student_42:")
