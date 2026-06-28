import logging
import time
from collections import defaultdict
from typing import Protocol

from fastapi import HTTPException, Request

from app.config import get_settings
from app.db.redis_client import get_redis_client

logger = logging.getLogger(__name__)

RATE_LIMIT_PREFIX = "rl:auth:"
AI_RATE_LIMIT_PREFIX = "rl:ai:"
PROGRESS_RATE_LIMIT_PREFIX = "rl:progress:"
TRANSCRIPT_IMPORT_RATE_LIMIT_PREFIX = "rl:transcript-import:"


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
    def __init__(self, redis_url: str, *, fail_closed: bool = True) -> None:
        self._redis_url = redis_url
        self._fail_closed = fail_closed

    async def is_allowed(self, key: str, *, window_ms: int, max_requests: int) -> bool:
        client = get_redis_client()
        if client is None:
            return await _fallback_store().is_allowed(
                key,
                window_ms=window_ms,
                max_requests=max_requests,
            )

        try:
            count = await client.incr(key)
            if count == 1:
                await client.pexpire(key, window_ms)
            return count <= max_requests
        except Exception:
            logger.warning("Redis rate limit failed for key %s; using fallback", key)
            if self._fail_closed:
                return await _fallback_store().is_allowed(
                    key,
                    window_ms=window_ms,
                    max_requests=max_requests,
                )
            return False


_in_memory_store = InMemoryRateLimitStore()
_store_override: RateLimitStore | None = None


def _fallback_store() -> InMemoryRateLimitStore:
    return _in_memory_store


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

    return RedisRateLimitStore(settings.redis_url, fail_closed=True)


def build_rate_limit_key(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{RATE_LIMIT_PREFIX}ip:{client_host}:{request.url.path}"


def build_email_rate_limit_key(*, email: str, path: str) -> str:
    normalized_email = str(email).strip().lower()
    return f"{RATE_LIMIT_PREFIX}email:{normalized_email}:{path}"


async def _enforce_rate_limit(
    *,
    key: str,
    window_ms: int,
    max_requests: int,
    detail: str,
) -> None:
    store = resolve_rate_limit_store()
    allowed = await store.is_allowed(
        key,
        window_ms=window_ms,
        max_requests=max_requests,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=detail)


async def enforce_auth_rate_limits(request: Request, *, email: str | None = None) -> None:
    settings = get_settings()
    detail = "Too many authentication requests. Please try again later."
    await _enforce_rate_limit(
        key=build_rate_limit_key(request),
        window_ms=settings.auth_rate_limit_window_ms,
        max_requests=settings.auth_rate_limit_max,
        detail=detail,
    )
    if email:
        await _enforce_rate_limit(
            key=build_email_rate_limit_key(email=email, path=request.url.path),
            window_ms=settings.auth_rate_limit_window_ms,
            max_requests=settings.auth_rate_limit_max,
            detail=detail,
        )


async def enforce_ai_rate_limit(request: Request, user_id: str) -> None:
    settings = get_settings()
    path = request.url.path
    key = f"{AI_RATE_LIMIT_PREFIX}{user_id}:{path}"
    await _enforce_rate_limit(
        key=key,
        window_ms=settings.ai_rate_limit_window_ms,
        max_requests=settings.ai_rate_limit_max,
        detail="Too many AI analysis requests. Please try again later.",
    )


async def enforce_progress_rate_limit(request: Request, user_id: str) -> None:
    settings = get_settings()
    path = request.url.path
    key = f"{PROGRESS_RATE_LIMIT_PREFIX}{user_id}:{path}"
    await _enforce_rate_limit(
        key=key,
        window_ms=settings.progress_rate_limit_window_ms,
        max_requests=settings.progress_rate_limit_max,
        detail="Too many progress requests. Please try again later.",
    )


async def enforce_transcript_import_rate_limit(request: Request, user_id: str) -> None:
    settings = get_settings()
    path = request.url.path
    key = f"{TRANSCRIPT_IMPORT_RATE_LIMIT_PREFIX}{user_id}:{path}"
    await _enforce_rate_limit(
        key=key,
        window_ms=settings.transcript_import_rate_limit_window_ms,
        max_requests=settings.transcript_import_rate_limit_max,
        detail="Too many transcript import requests. Please try again later.",
    )
