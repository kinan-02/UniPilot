import json
from unittest.mock import AsyncMock

import pytest

from app.security.outlook_oauth_state import (
    RedisOutlookOAuthStateStore,
    resolve_outlook_oauth_state_store,
    set_outlook_oauth_state_store,
)


@pytest.mark.asyncio
async def test_redis_outlook_oauth_state_store_roundtrip(monkeypatch):
    fake_client = AsyncMock()
    storage: dict[str, str] = {}

    async def setex(key, ttl, value):
        storage[key] = value

    async def getdel(key):
        return storage.pop(key, None)

    fake_client.setex = setex
    fake_client.getdel = getdel

    monkeypatch.setattr(
        "app.security.outlook_oauth_state.get_redis_client",
        lambda: fake_client,
    )
    set_outlook_oauth_state_store(None)
    store = RedisOutlookOAuthStateStore()
    await store.store("state", user_id="507f1f77bcf86cd799439011", code_verifier="verifier")
    consumed = await store.consume("state")
    assert consumed == ("507f1f77bcf86cd799439011", "verifier")


@pytest.mark.asyncio
async def test_redis_outlook_oauth_state_store_invalid_payload(monkeypatch):
    fake_client = AsyncMock()

    async def getdel(key):
        return json.dumps({"userId": "", "codeVerifier": ""})

    fake_client.getdel = getdel
    monkeypatch.setattr(
        "app.security.outlook_oauth_state.get_redis_client",
        lambda: fake_client,
    )
    store = RedisOutlookOAuthStateStore()
    assert await store.consume("state") is None


@pytest.mark.asyncio
async def test_redis_consume_without_client_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.security.outlook_oauth_state.get_redis_client",
        lambda: None,
    )
    store = RedisOutlookOAuthStateStore()
    assert await store.consume("state") is None


@pytest.mark.asyncio
async def test_redis_consume_missing_key_returns_none(monkeypatch):
    fake_client = AsyncMock()

    async def getdel(key):
        return None

    fake_client.getdel = getdel
    monkeypatch.setattr(
        "app.security.outlook_oauth_state.get_redis_client",
        lambda: fake_client,
    )
    store = RedisOutlookOAuthStateStore()
    assert await store.consume("state") is None


@pytest.mark.asyncio
async def test_redis_store_requires_client(monkeypatch):
    monkeypatch.setattr(
        "app.security.outlook_oauth_state.get_redis_client",
        lambda: None,
    )
    store = RedisOutlookOAuthStateStore()
    with pytest.raises(RuntimeError):
        await store.store("state", user_id="u", code_verifier="v")


def test_resolve_outlook_oauth_state_store_uses_override():
    class DummyStore:
        pass

    dummy = DummyStore()
    set_outlook_oauth_state_store(dummy)
    assert resolve_outlook_oauth_state_store() is dummy
    set_outlook_oauth_state_store(None)
