"""Live SSE stream for MAS negotiation replay events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.db.redis_client import get_redis_client
from app.repositories.agent_session_repository import find_agent_session_by_id_and_user

REPLAY_MAX_EVENTS = 64
TERMINAL_STATUSES = frozenset({"completed", "failed", "awaiting_clarification"})
POLL_INTERVAL_SECONDS = 1.5
MAX_STREAM_SECONDS = 300


def _replay_key(session_id: str) -> str:
    return f"mas:session:{session_id}:replay"


async def _load_replay_events(session_id: str) -> list[dict[str, Any]]:
    client = get_redis_client()
    if client is None:
        return []

    try:
        raw_events = await client.lrange(_replay_key(session_id), 0, REPLAY_MAX_EVENTS - 1)
    except Exception:  # noqa: BLE001
        return []

    events: list[dict[str, Any]] = []
    for raw in reversed(raw_events):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _format_sse_event(*, event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream_agent_session_events_for_user(
    database,
    *,
    user_id: str,
    session_id: str,
) -> AsyncIterator[str]:
    """
    Yield Server-Sent Events for new MAS replay phases until the session terminates.

    Reuses the Redis replay log written by the MAS worker during negotiation.
    """
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        yield _format_sse_event(event="error", data={"message": "Agent session not found"})
        return

    seen = 0
    elapsed = 0.0
    while elapsed <= MAX_STREAM_SECONDS:
        current = await find_agent_session_by_id_and_user(database, session_id, user_id)
        if current is None:
            yield _format_sse_event(event="error", data={"message": "Agent session not found"})
            return

        events = await _load_replay_events(session_id)
        while seen < len(events):
            item = events[seen]
            event_name = (
                "session_completed"
                if str(item.get("event") or "") == "session_completed"
                else "phase"
            )
            yield _format_sse_event(event=event_name, data=item)
            seen += 1

        status = str(current.get("status") or "")
        if status in TERMINAL_STATUSES:
            yield _format_sse_event(
                event="done",
                data={
                    "status": status,
                    "sessionId": session_id,
                    "eventCount": seen,
                },
            )
            return

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    yield _format_sse_event(
        event="timeout",
        data={"message": "Stream timed out before session completion.", "eventCount": seen},
    )
