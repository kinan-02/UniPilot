"""Turn-scoped tool-call result cache.

Found via a live-eval run: sibling nested sub-plans (different top-level
steps, each spinning up its own private task-handler sub-plan) have no way
to see what another sibling already fetched -- `get_entity(student_profile,
"student_123")` was called 40 times with identical arguments within a
single turn, `get_entity(course, "236756")` 24 times, `search_knowledge
("Machine Learning")` 20 times. The existing `tool_results_so_far` dict in
`RetrievalReasoningBlock`/`InterpretationReasoningBlock`/
`SimulationPlanningReasoningBlock` already de-duplicates within ONE round
loop, but that dict is thrown away the moment that one block instance
returns -- it never survives across the many separate block instances one
turn actually creates.

One `ToolCallCache` instance is created fresh per turn (`turn.py::
run_agent_turn`) and threaded down through every specialist dispatch --
atomic or nested, sibling or parent/child -- so any step reuses an
already-fetched result instead of paying for the tool call again. Never a
module-level global: a cache shared across turns/requests would leak one
student's data into another's, or serve stale results across turns.
"""

from __future__ import annotations

from typing import Any


class ToolCallCache:
    """Plain, mutable dict wrapper -- deliberately not a `BaseModel`, since
    this is a runtime-only collaborator (like `ToolRegistry`), never
    serialized or part of any schema."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._store[key] = value


__all__ = ["ToolCallCache"]
