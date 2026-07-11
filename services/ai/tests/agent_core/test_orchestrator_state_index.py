"""Unit tests for `app.agent_core.orchestrator.state_index` (extracted from
`orchestrator/loop.py`'s former private `_certainty_band`/`_build_state_index`
so `task_handler.py`'s nested Planner rounds can reuse the exact same logic)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.orchestrator.state_index import build_state_index, certainty_band
from app.agent_core.planning.state import CertaintyTag, StateEntry


def _entry(step_id: str, confidence: float) -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=confidence),
        produced_at=datetime.now(timezone.utc),
    )


def test_certainty_band_high_at_exactly_point_eight():
    assert certainty_band(0.8) == "high"


def test_certainty_band_medium_at_exactly_point_five():
    assert certainty_band(0.5) == "medium"


def test_certainty_band_medium_just_below_point_eight():
    assert certainty_band(0.79) == "medium"


def test_certainty_band_low_just_below_point_five():
    assert certainty_band(0.49) == "low"


def test_certainty_band_low_at_zero():
    assert certainty_band(0.0) == "low"


def test_build_state_index_preserves_order_and_maps_every_field():
    entries = [_entry("s1", 0.9), _entry("s2", 0.6), _entry("s3", 0.1)]
    summaries = build_state_index(entries)

    assert [s.step_id for s in summaries] == ["s1", "s2", "s3"]
    assert [s.certainty_band for s in summaries] == ["high", "medium", "low"]
    first = summaries[0]
    assert first.entry_id == "s1-0"
    assert first.role == "retrieval"
    assert first.summary == "succeeded (generic_step_output_v1)"


def test_build_state_index_of_empty_list_returns_empty():
    assert build_state_index([]) == []
