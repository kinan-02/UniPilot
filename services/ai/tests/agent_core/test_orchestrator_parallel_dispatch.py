"""Unit tests for `app.agent_core.orchestrator.parallel_dispatch`."""

from __future__ import annotations

import asyncio

import pytest

from app.agent_core.orchestrator.parallel_dispatch import dispatch_layer_concurrently


@pytest.mark.asyncio
async def test_preserves_input_order_even_when_completion_order_is_reversed():
    # "a" is artificially delayed so it completes LAST despite being first
    # in `items` -- proves the returned list follows `items`' own order, not
    # completion order.
    delays = {"a": 0.02, "b": 0.0}

    async def dispatch_one(item: str) -> str:
        await asyncio.sleep(delays[item])
        return item

    result = await dispatch_layer_concurrently(["a", "b"], dispatch_one)

    assert result == ["a", "b"]


@pytest.mark.asyncio
async def test_empty_items_returns_empty_without_invoking_dispatcher():
    calls: list[str] = []

    async def dispatch_one(item: str) -> str:
        calls.append(item)
        return item

    result = await dispatch_layer_concurrently([], dispatch_one)

    assert result == []
    assert calls == []


@pytest.mark.asyncio
async def test_runs_concurrently_not_sequentially():
    # Two 0.05s sleeps run concurrently should take ~0.05s total, not ~0.1s --
    # a real (not just structural) concurrency guarantee.
    async def dispatch_one(item: str) -> str:
        await asyncio.sleep(0.05)
        return item

    loop = asyncio.get_event_loop()
    start = loop.time()
    await dispatch_layer_concurrently(["a", "b"], dispatch_one)
    elapsed = loop.time() - start

    assert elapsed < 0.09
