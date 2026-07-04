"""Redis queue helpers for async AI jobs (in-memory fallback in test)."""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.db.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_in_memory_queue: list[str] = []


def reset_in_memory_ai_job_queue() -> None:
    _in_memory_queue.clear()


def _queue_name(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return (settings.worker_queue_name or "ai_jobs").strip() or "ai_jobs"


async def enqueue_ai_job(job_id: str, *, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client = get_redis_client()
    queue = _queue_name(settings)

    if client is None:
        _in_memory_queue.append(job_id)
        logger.debug("Enqueued AI job %s in in-memory queue", job_id)
        return

    await client.lpush(queue, job_id)
    logger.debug("Enqueued AI job %s on Redis queue %s", job_id, queue)


async def dequeue_ai_job(
    *,
    timeout_seconds: int = 5,
    settings: Settings | None = None,
) -> str | None:
    settings = settings or get_settings()
    client = get_redis_client()
    queue = _queue_name(settings)

    if client is None:
        if not _in_memory_queue:
            return None
        return _in_memory_queue.pop(0)

    result = await client.brpop(queue, timeout=timeout_seconds)
    if not result:
        return None
    _, job_id = result
    return str(job_id)
