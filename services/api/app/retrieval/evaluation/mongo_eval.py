"""MongoDB connectivity helpers for retrieval benchmark evaluation."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.db.mongo import check_mongo_connectivity, close_mongo_client, get_database

logger = logging.getLogger(__name__)


async def resolve_eval_database(
    *,
    settings: Settings | None = None,
    require: bool = False,
) -> Any | None:
    """Connect to MongoDB for offering eval cases, or return None when unavailable."""
    cfg = settings or get_settings()
    if not (cfg.mongo_uri or "").strip():
        message = "MONGO_URI is not configured; offering eval cases will be skipped"
        if require:
            raise SystemExit(message)
        logger.warning(message)
        return None

    status = await check_mongo_connectivity()
    if status != "connected":
        message = (
            "MongoDB is not reachable (start Docker: docker compose up -d mongo). "
            "Offering eval cases will be skipped."
        )
        if require:
            raise SystemExit(message)
        logger.warning(message)
        return None

    return await get_database()


async def close_eval_database() -> None:
    close_mongo_client()
