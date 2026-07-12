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


def test_build_state_index_includes_a_data_preview_when_data_is_non_empty():
    """The Planner used to see only pass/fail status, never a step's actual
    returned facts -- e.g. no way to tell a fetched-but-null program field
    apart from a step that simply failed for some unrelated reason. A bounded
    preview of `entry.data` is now folded into `summary` so the Planner's own
    "don't re-derive an already-confirmed-absent fact" instruction has
    something concrete to act on."""
    entry = StateEntry(
        entry_id="s1-0",
        step_id="s1",
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={"programSlug": None, "facultyId": None},
        certainty=CertaintyTag(basis="official_record", confidence=0.95),
        produced_at=datetime.now(timezone.utc),
    )

    summary = build_state_index([entry])[0].summary

    assert summary.startswith("succeeded (generic_step_output_v1): ")
    assert "programSlug" in summary
    assert "null" in summary


def test_build_state_index_truncates_an_oversized_data_preview():
    entry = StateEntry(
        entry_id="s1-0",
        step_id="s1",
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={"blob": "x" * 500},
        certainty=CertaintyTag(basis="official_record", confidence=0.95),
        produced_at=datetime.now(timezone.utc),
    )

    summary = build_state_index([entry])[0].summary

    assert summary.endswith("...(truncated)")
    assert len(summary) < 500
