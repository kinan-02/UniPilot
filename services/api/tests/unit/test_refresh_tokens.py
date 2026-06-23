"""Unit tests for refresh token stores and auth refresh edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.security.refresh_tokens as refresh_module
from app.security.refresh_tokens import (
    InMemoryRefreshTokenStore,
    RedisRefreshTokenStore,
    _decode_store_value,
    issue_refresh_token,
    reset_in_memory_refresh_token_store,
    revoke_refresh_token,
    set_refresh_token_store,
)


def test_decode_store_value_supports_legacy_plain_user_id() -> None:
    assert _decode_store_value("user-legacy") == ("user-legacy", False)


def test_decode_store_value_returns_none_without_user_id() -> None:
    assert _decode_store_value('{"rememberMe": true}') is None


@pytest.mark.asyncio
async def test_in_memory_consume_rejects_expired_entry() -> None:
    store = InMemoryRefreshTokenStore()
    token = "expired-token"
    store._entries[refresh_module._hash_token(token)] = (
        refresh_module._encode_store_value(user_id="user-1", remember_me=False),
        0,
    )
    assert await store.consume(token) is None


@pytest.mark.asyncio
async def test_redis_refresh_token_store_revoke_noop_without_client(monkeypatch) -> None:
    monkeypatch.setattr(refresh_module, "get_redis_client", lambda: None)
    store = RedisRefreshTokenStore()
    await store.revoke("token")


def test_resolve_refresh_token_store_returns_redis_store(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setattr(refresh_module, "_store_override", None)
    monkeypatch.setattr(
        refresh_module,
        "get_settings",
        lambda: Settings(
            environment="development",
            jwt_secret="secret",
            redis_url="redis://localhost:6379",
        ),
    )
    store = refresh_module.resolve_refresh_token_store()
    assert isinstance(store, RedisRefreshTokenStore)


def test_resolve_refresh_token_store_honors_override() -> None:
    fake_store = InMemoryRefreshTokenStore()
    set_refresh_token_store(fake_store)
    assert refresh_module.resolve_refresh_token_store() is fake_store
    set_refresh_token_store(None)


@pytest.mark.asyncio
async def test_in_memory_refresh_token_store_expires_entries() -> None:
    store = InMemoryRefreshTokenStore()
    store._entries["hash"] = (
        refresh_module._encode_store_value(user_id="user-1", remember_me=False),
        0,
    )
    assert await store.consume("unused") is None


@pytest.mark.asyncio
async def test_in_memory_refresh_token_store_revoke() -> None:
    store = InMemoryRefreshTokenStore()
    await store.store("token", user_id="user-1", remember_me=False)
    await store.revoke("token")
    assert await store.consume("token") is None


@pytest.mark.asyncio
async def test_redis_refresh_token_store_returns_none_for_missing_token(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.getdel = AsyncMock(return_value=None)
    monkeypatch.setattr(refresh_module, "get_redis_client", lambda: fake_client)

    store = RedisRefreshTokenStore()
    assert await store.consume("token") is None


@pytest.mark.asyncio
async def test_redis_refresh_token_store_round_trip(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.setex = AsyncMock()
    fake_client.getdel = AsyncMock(
        return_value=refresh_module._encode_store_value(user_id="user-42", remember_me=True)
    )
    fake_client.delete = AsyncMock()
    monkeypatch.setattr(refresh_module, "get_redis_client", lambda: fake_client)

    store = RedisRefreshTokenStore()
    await store.store("token", user_id="user-42", remember_me=True)
    assert await store.consume("token") == ("user-42", True)
    await store.revoke("token")
    fake_client.delete.assert_awaited()


@pytest.mark.asyncio
async def test_redis_refresh_token_store_returns_none_without_client(monkeypatch) -> None:
    monkeypatch.setattr(refresh_module, "get_redis_client", lambda: None)
    store = RedisRefreshTokenStore()
    assert await store.consume("token") is None


@pytest.mark.asyncio
async def test_redis_refresh_token_store_store_raises_without_client(monkeypatch) -> None:
    monkeypatch.setattr(refresh_module, "get_redis_client", lambda: None)
    store = RedisRefreshTokenStore()
    with pytest.raises(RuntimeError, match="Redis is required"):
        await store.store("token", user_id="user-1", remember_me=False)


@pytest.mark.asyncio
async def test_refresh_requires_cookie(auth_client):
    response = await auth_client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"] == "Refresh token is required"


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token(auth_client):
    response = await auth_client.post(
        "/auth/refresh",
        cookies={"unipilot_refresh_token": "invalid-token"},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["error"]


@pytest.mark.asyncio
async def test_refresh_rejects_token_for_deleted_user(auth_client):
    reset_in_memory_refresh_token_store()
    token = await issue_refresh_token(user_id="deadbeefdeadbeefdeadbeef")
    response = await auth_client.post(
        "/auth/refresh",
        cookies={"unipilot_refresh_token": token},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["error"]


def test_set_refresh_token_store_override() -> None:
    fake_store = InMemoryRefreshTokenStore()
    set_refresh_token_store(fake_store)
    assert refresh_module._store_override is fake_store
    set_refresh_token_store(None)


@pytest.mark.asyncio
async def test_revoke_refresh_token_is_noop_for_unknown_token() -> None:
    reset_in_memory_refresh_token_store()
    await revoke_refresh_token("missing")
