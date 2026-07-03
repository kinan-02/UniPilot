"""Unit tests for agent session SSE stream helpers."""

from __future__ import annotations

from app.services.agent_session_stream_service import _format_sse_event


def test_format_sse_event() -> None:
    payload = _format_sse_event(event="phase", data={"event": "goal_analyst"})
    assert payload.startswith("event: phase\n")
    assert '"goal_analyst"' in payload
    assert payload.endswith("\n\n")


def test_format_sse_session_completed_event() -> None:
    payload = _format_sse_event(
        event="session_completed",
        data={"event": "session_completed", "status": "completed"},
    )
    assert payload.startswith("event: session_completed\n")
    assert '"completed"' in payload
