"""Generic "dispatch one execution layer concurrently" utility.

`planning/rewrite.py::compute_plan_graph` already computes `execution_layers`
("steps safe to dispatch concurrently"), but nothing in `agent_core` actually
runs steps concurrently yet -- `orchestrator/loop.py` walks its own top-level
steps strictly sequentially. This is deliberately generic, not
task-handler-specific, so a later (currently out-of-scope) change to
`loop.py` could adopt the same utility for real top-level parallelism.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def dispatch_layer_concurrently(
    items: list[str],
    dispatch_one: Callable[[str], Awaitable[T]],
) -> list[T]:
    """Runs `dispatch_one` concurrently for every id in `items`; the returned
    list preserves `items`' own order regardless of completion order."""
    if not items:
        return []
    return list(await asyncio.gather(*(dispatch_one(item) for item in items)))


__all__ = ["dispatch_layer_concurrently"]
