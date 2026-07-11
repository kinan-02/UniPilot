"""Turns accumulated `StateEntry` records into the compact `StateEntrySummary`
index the Planner sees (docs/agent/AGENT_VISION.md §3.2, §8) -- never the
full payload, keeping the Planner's own context bounded.

Extracted from `orchestrator/loop.py`'s former private
`_certainty_band`/`_build_state_index` so `orchestrator/task_handler.py`'s
own private, nested Planner rounds can reuse the exact same logic rather
than duplicating it.
"""

from __future__ import annotations

from typing import Literal

from app.agent_core.planning.schemas import StateEntrySummary
from app.agent_core.planning.state import StateEntry


def certainty_band(confidence: float) -> Literal["high", "medium", "low"]:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def build_state_index(entries: list[StateEntry]) -> list[StateEntrySummary]:
    return [
        StateEntrySummary(
            entry_id=entry.entry_id,
            step_id=entry.step_id,
            role=entry.role,
            summary=f"{entry.status} ({entry.output_schema_name})",
            certainty_band=certainty_band(entry.certainty.confidence),
        )
        for entry in entries
    ]


__all__ = ["certainty_band", "build_state_index"]
