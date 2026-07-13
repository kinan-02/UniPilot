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
_DATA_PREVIEW_MAX_CHARS = 600

# How deep _shape_summary preserves every key name before giving up and
# collapsing the rest of a subtree -- 3 covers the shapes actually seen
# (e.g. entry.data -> "facts" -> {individual fields}).
_SHAPE_SUMMARY_MAX_DEPTH = 3
_SHAPE_SUMMARY_MAX_STRING_LEN = 40
_SHAPE_SUMMARY_MAX_LIST_ITEMS = 5


def certainty_band(confidence: float) -> Literal["high", "medium", "low"]:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _shape_summary(value: Any, *, depth: int = 0) -> Any:
    """Recursively preserves every dict key name (truncating only leaf
    values) up to `_SHAPE_SUMMARY_MAX_DEPTH` -- a flat character-count
    truncation of the raw JSON dump cuts off at an arbitrary byte position,
    silently hiding whichever fields happen to sort late enough (e.g.
    "year_of_study" never survives a truncated dump of a student profile
    once earlier fields already exceed the budget). Found via a live-eval
    run: the Planner kept re-scheduling a fact-fetch step it had already
    completed, because that fact's field name had been truncated out of
    every state_index preview it was ever shown. Which key exists at all
    matters far more to the Planner than a field's exact value, so key
    names are never sacrificed to make room for another field's full value.
    """
    if depth >= _SHAPE_SUMMARY_MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        return {key: _shape_summary(val, depth=depth + 1) for key, val in sorted(value.items())}
    if isinstance(value, list):
        preview = [_shape_summary(item, depth=depth + 1) for item in value[:_SHAPE_SUMMARY_MAX_LIST_ITEMS]]
        if len(value) > _SHAPE_SUMMARY_MAX_LIST_ITEMS:
            preview.append(f"...(+{len(value) - _SHAPE_SUMMARY_MAX_LIST_ITEMS} more)")
        return preview
    if isinstance(value, str) and len(value) > _SHAPE_SUMMARY_MAX_STRING_LEN:
        return f"{value[:_SHAPE_SUMMARY_MAX_STRING_LEN]}…"
    return value


def _data_preview(data: dict[str, Any]) -> str:
    if not data:
        return ""
    text = json.dumps(data, ensure_ascii=False, default=str, sort_keys=True)
    if len(text) <= _DATA_PREVIEW_MAX_CHARS:
        return text

    summarized_text = json.dumps(_shape_summary(data), ensure_ascii=False, default=str, sort_keys=True)
    if len(summarized_text) > _DATA_PREVIEW_MAX_CHARS:
        summarized_text = summarized_text[:_DATA_PREVIEW_MAX_CHARS]
    return f"{summarized_text}...(truncated)"


def build_state_index(entries: list[StateEntry]) -> list[StateEntrySummary]:
    summaries = []
    for entry in entries:
        base = f"{entry.status} ({entry.output_schema_name})"
        preview = _data_preview(entry.data)
        
        if entry.status != "succeeded" and entry.warnings:
            unique_warnings = list(dict.fromkeys(entry.warnings))
            warnings_preview = _data_preview({"warnings": unique_warnings})
            if preview:
                preview = f"{preview} | {warnings_preview}"
            else:
                preview = warnings_preview
                
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
