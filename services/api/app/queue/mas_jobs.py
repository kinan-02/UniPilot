"""Redis queue publisher for MAS agent session jobs."""

from __future__ import annotations

import json

from app.config import get_settings
from app.db.redis_client import get_redis_client


async def enqueue_mas_session(session_id: str) -> bool:
    settings = get_settings()
    client = get_redis_client()
    if client is None:
        return False

    payload = json.dumps({"sessionId": session_id})
    await client.lpush(settings.mas_queue_name, payload)
    return True
