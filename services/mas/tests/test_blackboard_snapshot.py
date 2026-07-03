"""Unit tests for blackboard replay log."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.orchestrator.blackboard import Blackboard
from app.services.blackboard_snapshot import (
    load_replay_events,
    persist_blackboard_snapshot,
    persist_session_completion_event,
)


@pytest.mark.asyncio
async def test_persist_blackboard_snapshot_appends_replay_log() -> None:
    board = Blackboard(goal="plan next semester")
    mock_client = AsyncMock()

    with patch("app.services.blackboard_snapshot.get_redis_client", return_value=mock_client):
        await persist_blackboard_snapshot(session_id="abc123", blackboard=board, event="goal_analyst")

    mock_client.set.assert_awaited_once()
    mock_client.lpush.assert_awaited_once()
    mock_client.ltrim.assert_awaited_once()
    mock_client.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_replay_events_returns_oldest_first() -> None:
    mock_client = AsyncMock()
    mock_client.lrange = AsyncMock(
        return_value=[
            '{"event":"planner_round_1"}',
            '{"event":"goal_analyst"}',
        ]
    )

    with patch("app.services.blackboard_snapshot.get_redis_client", return_value=mock_client):
        events = await load_replay_events("abc123")

    assert [event["event"] for event in events] == ["goal_analyst", "planner_round_1"]


@pytest.mark.asyncio
async def test_persist_session_completion_event_appends_without_snapshot() -> None:
    mock_client = AsyncMock()

    with patch("app.services.blackboard_snapshot.get_redis_client", return_value=mock_client):
        await persist_session_completion_event(
            session_id="abc123",
            status="completed",
            rounds=2,
            final_decision={"course_ids": ["00140008"]},
        )

    mock_client.set.assert_not_awaited()
    mock_client.lpush.assert_awaited_once()
    pushed_payload = mock_client.lpush.await_args.args[1]
    assert '"session_completed"' in pushed_payload
    assert '"completed"' in pushed_payload
