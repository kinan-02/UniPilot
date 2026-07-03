"""SSE formatting for agent streaming events (spec §26)."""

from __future__ import annotations

import json
from typing import Any

from app.agent.schemas import StreamEvent


def format_sse_event(event: StreamEvent) -> str:
    payload = event.to_sse_payload()
    event_name = str(payload.get("type") or "message")
    return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"


def format_sse_error(message: str) -> str:
    return format_sse_event(
        StreamEvent(type="run.failed", error=message, label=message),
    )
