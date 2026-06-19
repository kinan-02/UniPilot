import redis.asyncio as redis

from app.config import get_settings


async def check_redis_connectivity() -> str:
    settings = get_settings()
    if not settings.redis_url:
        return "not_configured"

    client = redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        await client.ping()
        return "connected"
    except Exception:
        return "disconnected"
    finally:
        await client.aclose()
