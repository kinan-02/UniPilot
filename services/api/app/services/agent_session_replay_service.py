"""Load MAS negotiation replay events from Redis."""

from __future__ import annotations

import json
from typing import Any

from app.db.redis import get_redis_client
from app.repositories.agent_session_repository import find_agent_session_by_id_and_user

REPLAY_MAX_EVENTS = 64


def _replay_key(session_id: str) -> str:
    return f"mas:session:{session_id}:replay"


async def get_agent_session_replay_for_user(
    database,
    *,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}

    client = get_redis_client()
    if client is None:
        return {"status": "ok", "events": [], "replayAvailable": False}

    try:
        raw_events = await client.lrange(_replay_key(session_id), 0, REPLAY_MAX_EVENTS - 1)
    except Exception:  # noqa: BLE001
        return {"status": "ok", "events": [], "replayAvailable": False}

    events: list[dict[str, Any]] = []
    for raw in reversed(raw_events):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)

    return {
        "status": "ok",
        "events": events,
        "replayAvailable": bool(events),
    }
