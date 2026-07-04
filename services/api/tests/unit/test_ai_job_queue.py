"""Unit tests for AI job queue fallback."""

from __future__ import annotations

import pytest

from app.services.ai_job_queue import (
    dequeue_ai_job,
    enqueue_ai_job,
    reset_in_memory_ai_job_queue,
)


@pytest.mark.asyncio
async def test_in_memory_queue_round_trip(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    reset_in_memory_ai_job_queue()

    await enqueue_ai_job("job-1")
    await enqueue_ai_job("job-2")

    first = await dequeue_ai_job()
    second = await dequeue_ai_job()
    empty = await dequeue_ai_job()

    assert first == "job-1"
    assert second == "job-2"
    assert empty is None
