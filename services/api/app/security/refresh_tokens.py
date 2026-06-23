import hashlib
import json
import secrets
import time
from typing import Protocol

from app.config import get_settings
from app.db.redis_client import get_redis_client

REFRESH_TOKEN_PREFIX = "rt:"


class RefreshTokenStore(Protocol):
    async def store(self, token: str, *, user_id: str, remember_me: bool) -> None: ...

    async def consume(self, token: str) -> tuple[str, bool] | None: ...

    async def revoke(self, token: str) -> None: ...


def refresh_token_ttl_seconds(*, remember_me: bool) -> int:
    settings = get_settings()
    if remember_me:
        return int(settings.refresh_token_remember_ttl_seconds)
    return int(settings.refresh_token_session_ttl_seconds)


def _encode_store_value(*, user_id: str, remember_me: bool) -> str:
    return json.dumps({"userId": user_id, "rememberMe": remember_me})


def _decode_store_value(raw: str) -> tuple[str, bool] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return str(raw), False
    user_id = payload.get("userId")
    if not user_id:
        return None
    return str(user_id), bool(payload.get("rememberMe"))


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

    async def store(self, token: str, *, user_id: str, remember_me: bool) -> None:
        self._purge_expired()
        token_hash = _hash_token(token)
        ttl = refresh_token_ttl_seconds(remember_me=remember_me)
        self._entries[token_hash] = (
            _encode_store_value(user_id=user_id, remember_me=remember_me),
            time.time() + ttl,
        )

    async def consume(self, token: str) -> tuple[str, bool] | None:
        self._purge_expired()
        token_hash = _hash_token(token)
        entry = self._entries.pop(token_hash, None)
        if entry is None:
            return None
        raw_value, _expires_at = entry
        return _decode_store_value(raw_value)

    async def revoke(self, token: str) -> None:
        self._purge_expired()
        self._entries.pop(_hash_token(token), None)

    def reset(self) -> None:
        self._entries.clear()


class RedisRefreshTokenStore:
    async def store(self, token: str, *, user_id: str, remember_me: bool) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is required for refresh token storage")

        ttl = refresh_token_ttl_seconds(remember_me=remember_me)
        await client.setex(
            f"{REFRESH_TOKEN_PREFIX}{_hash_token(token)}",
            ttl,
            _encode_store_value(user_id=user_id, remember_me=remember_me),
        )

    async def consume(self, token: str) -> tuple[str, bool] | None:
        client = get_redis_client()
        if client is None:
            return None

        key = f"{REFRESH_TOKEN_PREFIX}{_hash_token(token)}"
        raw_value = await client.getdel(key)
        if not raw_value:
            return None
        return _decode_store_value(str(raw_value))

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


async def issue_refresh_token(*, user_id: str, remember_me: bool = False) -> str:
    token = generate_refresh_token()
    store = resolve_refresh_token_store()
    await store.store(token, user_id=user_id, remember_me=remember_me)
    return token


async def rotate_refresh_token(token: str) -> tuple[str, str, bool] | None:
    store = resolve_refresh_token_store()
    consumed = await store.consume(token)
    if consumed is None:
        return None

    user_id, remember_me = consumed
    new_token = await issue_refresh_token(user_id=user_id, remember_me=remember_me)
    return user_id, new_token, remember_me


async def revoke_refresh_token(token: str) -> None:
    store = resolve_refresh_token_store()
    await store.revoke(token)
