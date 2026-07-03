"""Background Redis consumer for MAS agent sessions."""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.db.redis_client import get_redis_client
from app.sessions.processor import process_session

logger = logging.getLogger(__name__)


async def run_worker_loop() -> None:
    settings = get_settings()
    if not settings.mas_worker_enabled:
        logger.info("MAS worker disabled (MAS_WORKER_ENABLED=false)")
        return

    client = get_redis_client()
    if client is None:
        logger.warning("MAS worker cannot start: REDIS_URL is not configured")
        return

    queue = settings.mas_queue_name
    logger.info("MAS worker listening on queue=%s", queue)

    while True:
        try:
            item = await client.brpop(queue, timeout=5)
            if not item:
                continue
            _queue_name, payload = item
            data = json.loads(payload)
            session_id = str(data.get("sessionId") or "")
            if not session_id:
                logger.warning("Skipping job with missing sessionId: %s", payload)
                continue
            logger.info("Processing MAS session %s", session_id)
            await process_session(session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("MAS worker job failed")
            await asyncio.sleep(1)
