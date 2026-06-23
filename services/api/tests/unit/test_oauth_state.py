"""Unit tests for OAuth CSRF state storage."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.security.oauth_state as oauth_state_module
from app.security.oauth_state import (
    RedisOAuthStateStore,
    consume_oauth_state,
    issue_oauth_state,
    reset_in_memory_oauth_state_store,
)


@pytest.mark.asyncio
async def test_oauth_state_is_single_use():
    reset_in_memory_oauth_state_store()
    state = await issue_oauth_state(remember_me=True)
    assert await consume_oauth_state(state) is True
    assert await consume_oauth_state(state) is None


@pytest.mark.asyncio
async def test_oauth_state_stores_remember_me_flag():
    reset_in_memory_oauth_state_store()
    state = await issue_oauth_state(remember_me=False)
    assert await consume_oauth_state(state) is False


@pytest.mark.asyncio
async def test_redis_oauth_state_store_round_trip(monkeypatch):
    fake_client = AsyncMock()
    fake_client.setex = AsyncMock()
    fake_client.getdel = AsyncMock(return_value="1")
    monkeypatch.setattr(oauth_state_module, "get_redis_client", lambda: fake_client)

    store = RedisOAuthStateStore()
    await store.store("state-token", remember_me=True)
    assert await store.consume("state-token") is True


@pytest.mark.asyncio
async def test_in_memory_oauth_state_purges_expired_entries():
    store = oauth_state_module.InMemoryOAuthStateStore()
    store._entries["expired"] = (False, 0)
    await store.store("fresh", remember_me=True)
    assert "expired" not in store._entries


@pytest.mark.asyncio
async def test_redis_oauth_state_store_requires_client_for_store(monkeypatch):
    monkeypatch.setattr(oauth_state_module, "get_redis_client", lambda: None)
    store = RedisOAuthStateStore()
    with pytest.raises(RuntimeError, match="Redis is required"):
        await store.store("state-token", remember_me=False)


@pytest.mark.asyncio
async def test_redis_oauth_state_store_returns_none_without_client(monkeypatch):
    monkeypatch.setattr(oauth_state_module, "get_redis_client", lambda: None)
    store = RedisOAuthStateStore()
    assert await store.consume("state-token") is None


@pytest.mark.asyncio
async def test_redis_oauth_state_store_returns_none_for_missing_state(monkeypatch):
    fake_client = AsyncMock()
    fake_client.getdel = AsyncMock(return_value=None)
    monkeypatch.setattr(oauth_state_module, "get_redis_client", lambda: fake_client)
    store = RedisOAuthStateStore()
    assert await store.consume("missing") is None


def test_resolve_oauth_state_store_uses_redis_in_development(monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(oauth_state_module, "_store_override", None)
    settings = Settings(
        environment="development",
        jwt_secret="secret",
        redis_url="redis://localhost:6379",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    store = oauth_state_module.resolve_oauth_state_store()
    assert isinstance(store, RedisOAuthStateStore)


def test_set_oauth_state_store_override():
    fake_store = oauth_state_module.InMemoryOAuthStateStore()
    oauth_state_module.set_oauth_state_store(fake_store)
    assert oauth_state_module._store_override is fake_store
    assert oauth_state_module.resolve_oauth_state_store() is fake_store
    oauth_state_module.set_oauth_state_store(None)
