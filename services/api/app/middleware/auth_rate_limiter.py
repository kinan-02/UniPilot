import time
from collections import defaultdict
from typing import Protocol

import redis.asyncio as redis
from fastapi import HTTPException, Request

from app.config import get_settings

RATE_LIMIT_PREFIX = "rl:auth:"


class RateLimitStore(Protocol):
    async def is_allowed(self, key: str, *, window_ms: int, max_requests: int) -> bool: ...


class InMemoryRateLimitStore:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def is_allowed(self, key: str, *, window_ms: int, max_requests: int) -> bool:
        now_ms = time.time() * 1000
        window_start = now_ms - window_ms
        hits = [timestamp for timestamp in self._hits[key] if timestamp > window_start]

        if len(hits) >= max_requests:
            self._hits[key] = hits
            return False

        hits.append(now_ms)
        self._hits[key] = hits
        return True

    def reset(self) -> None:
        self._hits.clear()


class RedisRateLimitStore:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def is_allowed(self, key: str, *, window_ms: int, max_requests: int) -> bool:
        client = redis.from_url(
            self._redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

        try:
            count = await client.incr(key)
            if count == 1:
                await client.pexpire(key, window_ms)
            return count <= max_requests
        finally:
            await client.aclose()


_in_memory_store = InMemoryRateLimitStore()
_store_override: RateLimitStore | None = None


def set_rate_limit_store(store: RateLimitStore | None) -> None:
    global _store_override
    _store_override = store


def reset_in_memory_rate_limit_store() -> None:
    _in_memory_store.reset()


def resolve_rate_limit_store() -> RateLimitStore:
    if _store_override is not None:
        return _store_override

    settings = get_settings()
    if settings.environment == "test" or not settings.redis_url:
        return _in_memory_store

    return RedisRateLimitStore(settings.redis_url)


def build_rate_limit_key(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{RATE_LIMIT_PREFIX}{client_host}:{request.url.path}"


async def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    store = resolve_rate_limit_store()
    key = build_rate_limit_key(request)

    allowed = await store.is_allowed(
        key,
        window_ms=settings.auth_rate_limit_window_ms,
        max_requests=settings.auth_rate_limit_max,
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many authentication requests. Please try again later.",
        )
