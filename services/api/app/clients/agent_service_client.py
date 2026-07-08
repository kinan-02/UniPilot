"""HTTP(streaming) client for the internal `agent` service.

`api` remains the only client-facing entry point: it authenticates the
student, persists the user message, then forwards the turn to the internal
`agent` service and streams its raw SSE response straight back to the
client. `api` never re-parses/re-serializes the events — the `agent`
service already formats them with the same `format_sse_event` shape the
frontend has always received.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings, get_settings


def format_sse_error(message: str) -> str:
    """Match `app.agent.streaming.format_sse_event` for a `run.failed` event.

    Duplicated (not imported) intentionally: `app/agent` no longer lives in
    `api` — this is the one SSE event `api` itself must be able to emit
    before ever reaching the `agent` service (e.g. conversation not found).
    """
    payload = {"type": "run.failed", "error": message}
    return f"event: run.failed\ndata: {json.dumps(payload)}\n\n"


async def stream_agent_turn(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    trigger_message_id: str,
    message_attachments: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Stream one agent turn from the internal `agent` service.

    Yields raw SSE text chunks exactly as produced by the `agent` service.
    Never raises — connection/timeout/non-200 failures are surfaced as a
    single `run.failed` SSE event so the caller's stream always terminates
    cleanly.
    """
    cfg = settings or get_settings()
    url = f"{cfg.resolved_agent_service_url()}/turn"
    token = cfg.resolved_internal_service_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Internal-Service-Token"] = token

    payload = {
        "userId": user_id,
        "conversationId": conversation_id,
        "userMessage": user_message,
        "triggerMessageId": trigger_message_id,
        "messageAttachments": message_attachments or [],
    }

    timeout = httpx.Timeout(cfg.agent_turn_timeout_seconds, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="ignore")[:300] or "agent service error"
                    yield format_sse_error(f"Agent service request failed: {detail}")
                    return
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk
    except httpx.HTTPError as exc:
        yield format_sse_error(f"Agent service unavailable: {exc}")
