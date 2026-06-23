"""Short-lived OAuth CSRF state storage."""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Protocol

from app.db.redis_client import get_redis_client

OAUTH_STATE_PREFIX = "oauth_state:"
OAUTH_STATE_TTL_SECONDS = 10 * 60


class OAuthStateStore(Protocol):
    async def store(self, state: str, *, remember_me: bool) -> None: ...

    async def consume(self, state: str) -> bool | None: ...


class InMemoryOAuthStateStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[bool, float]] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, (_, expires_at) in self._entries.items() if expires_at <= now]
        for key in expired:
            del self._entries[key]

    async def store(self, state: str, *, remember_me: bool) -> None:
        self._purge_expired()
        self._entries[_hash_state(state)] = (
            remember_me,
            time.time() + OAUTH_STATE_TTL_SECONDS,
        )

    async def consume(self, state: str) -> bool | None:
        self._purge_expired()
        entry = self._entries.pop(_hash_state(state), None)
        if entry is None:
            return None
        remember_me, _expires_at = entry
        return remember_me

    def reset(self) -> None:
        self._entries.clear()


class RedisOAuthStateStore:
    async def store(self, state: str, *, remember_me: bool) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is required for OAuth state storage")

        await client.setex(
            f"{OAUTH_STATE_PREFIX}{_hash_state(state)}",
            OAUTH_STATE_TTL_SECONDS,
            "1" if remember_me else "0",
        )

    async def consume(self, state: str) -> bool | None:
        client = get_redis_client()
        if client is None:
            return None

        raw = await client.getdel(f"{OAUTH_STATE_PREFIX}{_hash_state(state)}")
        if raw is None:
            return None
        return str(raw) == "1"


_in_memory_store = InMemoryOAuthStateStore()
_store_override: OAuthStateStore | None = None


def _hash_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def set_oauth_state_store(store: OAuthStateStore | None) -> None:
    global _store_override
    _store_override = store


def reset_in_memory_oauth_state_store() -> None:
    _in_memory_store.reset()


def resolve_oauth_state_store() -> OAuthStateStore:
    if _store_override is not None:
        return _store_override

    from app.config import get_settings

    settings = get_settings()
    if settings.environment == "test" or not settings.redis_url:
        return _in_memory_store

    return RedisOAuthStateStore()


async def issue_oauth_state(*, remember_me: bool) -> str:
    state = generate_oauth_state()
    store = resolve_oauth_state_store()
    await store.store(state, remember_me=remember_me)
    return state


async def consume_oauth_state(state: str) -> bool | None:
    store = resolve_oauth_state_store()
    return await store.consume(state)
