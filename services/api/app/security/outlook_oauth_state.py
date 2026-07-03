"""Short-lived Microsoft Outlook OAuth PKCE state storage."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Protocol

from app.db.redis_client import get_redis_client

OUTLOOK_OAUTH_STATE_PREFIX = "outlook_oauth_state:"
OUTLOOK_OAUTH_STATE_TTL_SECONDS = 10 * 60


class OutlookOAuthStateStore(Protocol):
    async def store(
        self,
        state: str,
        *,
        user_id: str,
        code_verifier: str,
    ) -> None: ...

    async def consume(self, state: str) -> tuple[str, str] | None: ...


class InMemoryOutlookOAuthStateStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, str, float]] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, (_, _, expires_at) in self._entries.items() if expires_at <= now]
        for key in expired:
            del self._entries[key]

    async def store(
        self,
        state: str,
        *,
        user_id: str,
        code_verifier: str,
    ) -> None:
        self._purge_expired()
        self._entries[_hash_state(state)] = (
            user_id,
            code_verifier,
            time.time() + OUTLOOK_OAUTH_STATE_TTL_SECONDS,
        )

    async def consume(self, state: str) -> tuple[str, str] | None:
        self._purge_expired()
        entry = self._entries.pop(_hash_state(state), None)
        if entry is None:
            return None
        user_id, code_verifier, _expires_at = entry
        return user_id, code_verifier

    def reset(self) -> None:
        self._entries.clear()


class RedisOutlookOAuthStateStore:
    async def store(
        self,
        state: str,
        *,
        user_id: str,
        code_verifier: str,
    ) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is required for Outlook OAuth state storage")

        payload = json.dumps({"userId": user_id, "codeVerifier": code_verifier})
        await client.setex(
            f"{OUTLOOK_OAUTH_STATE_PREFIX}{_hash_state(state)}",
            OUTLOOK_OAUTH_STATE_TTL_SECONDS,
            payload,
        )

    async def consume(self, state: str) -> tuple[str, str] | None:
        client = get_redis_client()
        if client is None:
            return None

        raw = await client.getdel(f"{OUTLOOK_OAUTH_STATE_PREFIX}{_hash_state(state)}")
        if raw is None:
            return None
        parsed = json.loads(str(raw))
        user_id = str(parsed.get("userId", "")).strip()
        code_verifier = str(parsed.get("codeVerifier", "")).strip()
        if not user_id or not code_verifier:
            return None
        return user_id, code_verifier


_in_memory_store = InMemoryOutlookOAuthStateStore()
_store_override: OutlookOAuthStateStore | None = None


def _hash_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def set_outlook_oauth_state_store(store: OutlookOAuthStateStore | None) -> None:
    global _store_override
    _store_override = store


def reset_in_memory_outlook_oauth_state_store() -> None:
    _in_memory_store.reset()


def resolve_outlook_oauth_state_store() -> OutlookOAuthStateStore:
    if _store_override is not None:
        return _store_override

    from app.config import get_settings

    settings = get_settings()
    if settings.environment == "test" or not settings.redis_url:
        return _in_memory_store

    return RedisOutlookOAuthStateStore()


async def issue_outlook_oauth_state(*, user_id: str, code_verifier: str) -> str:
    state = generate_oauth_state()
    store = resolve_outlook_oauth_state_store()
    await store.store(state, user_id=user_id, code_verifier=code_verifier)
    return state


async def consume_outlook_oauth_state(state: str) -> tuple[str, str] | None:
    store = resolve_outlook_oauth_state_store()
    return await store.consume(state)
