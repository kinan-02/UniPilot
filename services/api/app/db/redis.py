import redis.asyncio as redis

from app.config import get_settings
from app.db.redis_client import check_redis_connectivity as _check_pool_connectivity
from app.db.redis_client import close_redis_client, get_redis_client


async def check_redis_connectivity() -> str:
    return await _check_pool_connectivity()


async def close_redis() -> None:
    await close_redis_client()


__all__ = ["check_redis_connectivity", "close_redis", "get_redis_client"]
