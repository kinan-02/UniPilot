import hashlib
import secrets
import time
from typing import Protocol

from app.config import get_settings
from app.db.redis_client import get_redis_client

REFRESH_TOKEN_PREFIX = "rt:"
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


class RefreshTokenStore(Protocol):
    async def store(self, token: str, *, user_id: str) -> None: ...

    async def consume(self, token: str) -> str | None: ...

    async def revoke(self, token: str) -> None: ...


class InMemoryRefreshTokenStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float]] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired_keys = [
            key for key, (_, expires_at) in self._entries.items() if expires_at <= now
        ]
        for key in expired_keys:
            del self._entries[key]

    async def store(self, token: str, *, user_id: str) -> None:
        self._purge_expired()
        token_hash = _hash_token(token)
        self._entries[token_hash] = (user_id, time.time() + REFRESH_TOKEN_TTL_SECONDS)

    async def consume(self, token: str) -> str | None:
        self._purge_expired()
        token_hash = _hash_token(token)
        entry = self._entries.pop(token_hash, None)
        if entry is None:
            return None
        user_id, _expires_at = entry
        return user_id

    async def revoke(self, token: str) -> None:
        self._purge_expired()
        self._entries.pop(_hash_token(token), None)

    def reset(self) -> None:
        self._entries.clear()


class RedisRefreshTokenStore:
    async def store(self, token: str, *, user_id: str) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is required for refresh token storage")

        await client.setex(
            f"{REFRESH_TOKEN_PREFIX}{_hash_token(token)}",
            REFRESH_TOKEN_TTL_SECONDS,
            user_id,
        )

    async def consume(self, token: str) -> str | None:
        client = get_redis_client()
        if client is None:
            return None

        key = f"{REFRESH_TOKEN_PREFIX}{_hash_token(token)}"
        user_id = await client.getdel(key)
        return str(user_id) if user_id else None

    async def revoke(self, token: str) -> None:
        client = get_redis_client()
        if client is None:
            return

        await client.delete(f"{REFRESH_TOKEN_PREFIX}{_hash_token(token)}")


_in_memory_store = InMemoryRefreshTokenStore()
_store_override: RefreshTokenStore | None = None


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def set_refresh_token_store(store: RefreshTokenStore | None) -> None:
    global _store_override
    _store_override = store


def reset_in_memory_refresh_token_store() -> None:
    _in_memory_store.reset()


def resolve_refresh_token_store() -> RefreshTokenStore:
    if _store_override is not None:
        return _store_override

    settings = get_settings()
    if settings.environment == "test" or not settings.redis_url:
        return _in_memory_store

    return RedisRefreshTokenStore()


async def issue_refresh_token(*, user_id: str) -> str:
    token = generate_refresh_token()
    store = resolve_refresh_token_store()
    await store.store(token, user_id=user_id)
    return token


async def rotate_refresh_token(token: str) -> tuple[str, str] | None:
    store = resolve_refresh_token_store()
    user_id = await store.consume(token)
    if not user_id:
        return None

    new_token = await issue_refresh_token(user_id=user_id)
    return user_id, new_token


async def revoke_refresh_token(token: str) -> None:
    store = resolve_refresh_token_store()
    await store.revoke(token)
