"""Redis client for MAS job queue."""

from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis | None:
    global _redis_client

    settings = get_settings()
    if not settings.redis_url:
        return None

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
