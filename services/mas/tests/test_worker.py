"""Unit tests for the MAS Redis worker loop."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker import run_worker_loop


@pytest.mark.asyncio
async def test_run_worker_loop_exits_when_disabled() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = False

    with patch("app.worker.get_settings", return_value=settings):
        await run_worker_loop()


@pytest.mark.asyncio
async def test_run_worker_loop_exits_when_redis_missing() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = True

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.get_redis_client", return_value=None),
    ):
        await run_worker_loop()


@pytest.mark.asyncio
async def test_run_worker_loop_processes_valid_job() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = True
    settings.mas_queue_name = "mas_agent_jobs"

    client = AsyncMock()
    client.brpop = AsyncMock(
        side_effect=[
            ("mas_agent_jobs", json.dumps({"sessionId": "abc123"})),
            asyncio.CancelledError(),
        ]
    )

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.get_redis_client", return_value=client),
        patch("app.worker.process_session", new=AsyncMock()) as process_session,
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_worker_loop()

    process_session.assert_awaited_once_with("abc123")


@pytest.mark.asyncio
async def test_run_worker_loop_skips_missing_session_id() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = True
    settings.mas_queue_name = "mas_agent_jobs"

    client = AsyncMock()
    client.brpop = AsyncMock(
        side_effect=[
            ("mas_agent_jobs", json.dumps({})),
            asyncio.CancelledError(),
        ]
    )

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.get_redis_client", return_value=client),
        patch("app.worker.process_session", new=AsyncMock()) as process_session,
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_worker_loop()

    process_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_worker_loop_ignores_empty_queue_poll() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = True
    settings.mas_queue_name = "mas_agent_jobs"

    client = AsyncMock()
    client.brpop = AsyncMock(
        side_effect=[
            None,
            asyncio.CancelledError(),
        ]
    )

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.get_redis_client", return_value=client),
        patch("app.worker.process_session", new=AsyncMock()) as process_session,
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_worker_loop()

    process_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_worker_loop_recovers_from_job_failure() -> None:
    settings = MagicMock()
    settings.mas_worker_enabled = True
    settings.mas_queue_name = "mas_agent_jobs"

    client = AsyncMock()
    client.brpop = AsyncMock(
        side_effect=[
            ("mas_agent_jobs", json.dumps({"sessionId": "bad"})),
            asyncio.CancelledError(),
        ]
    )

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.get_redis_client", return_value=client),
        patch("app.worker.process_session", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.worker.asyncio.sleep", new=AsyncMock()) as sleep_mock,
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_worker_loop()

    sleep_mock.assert_awaited_once_with(1)
