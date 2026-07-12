"""Turns accumulated `StateEntry` records into the compact `StateEntrySummary`
index the Planner sees (docs/agent/AGENT_VISION.md §3.2, §8) -- never the
full payload, keeping the Planner's own context bounded.

Extracted from `orchestrator/loop.py`'s former private
`_certainty_band`/`_build_state_index` so `orchestrator/task_handler.py`'s
own private, nested Planner rounds can reuse the exact same logic rather
than duplicating it.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from app.agent_core.planning.schemas import StateEntrySummary
from app.agent_core.planning.state import StateEntry

# Bounds how much of a step's actual returned data leaks into the Planner's
# context per entry -- enough to see e.g. "programSlug: null" (the concrete
# fact that lets the Planner's own instructions recognize an already-
# conclusively-resolved-absent value and stop re-scheduling steps to
# re-derive it), never the raw, unbounded tool payload.
_DATA_PREVIEW_MAX_CHARS = 240


def certainty_band(confidence: float) -> Literal["high", "medium", "low"]:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _data_preview(data: dict[str, Any]) -> str:
    if not data:
        return ""
    text = json.dumps(data, ensure_ascii=False, default=str, sort_keys=True)
    if len(text) > _DATA_PREVIEW_MAX_CHARS:
        text = f"{text[:_DATA_PREVIEW_MAX_CHARS]}...(truncated)"
    return text


def build_state_index(entries: list[StateEntry]) -> list[StateEntrySummary]:
    summaries = []
    for entry in entries:
        base = f"{entry.status} ({entry.output_schema_name})"
        preview = _data_preview(entry.data)
        summaries.append(
            StateEntrySummary(
                entry_id=entry.entry_id,
                step_id=entry.step_id,
                role=entry.role,
                summary=f"{base}: {preview}" if preview else base,
                certainty_band=certainty_band(entry.certainty.confidence),
            )
        )
    return summaries


__all__ = ["certainty_band", "build_state_index"]
