"""Unit tests for `app.agent_core.planning.state` (docs/agent/AGENT_VISION.md §3.2, §8)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.planning.state import CertaintyTag, PlanExecutionState, StateEntry


def _entry(step_id: str, entry_id: str | None = None) -> StateEntry:
    return StateEntry(
        entry_id=entry_id or f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )


def test_append_only_a_retry_appends_a_second_entry_not_overwrite():
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("s1", "s1-0"))
    state.append(_entry("s1", "s1-1"))  # retried after a replan
    assert len(state.entries) == 2
    assert [e.entry_id for e in state.entries] == ["s1-0", "s1-1"]


def test_by_step_returns_the_most_recent_entry_for_a_step_id():
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("s1", "s1-0"))
    state.append(_entry("s1", "s1-1"))
    latest = state.by_step("s1")
    assert latest is not None
    assert latest.entry_id == "s1-1"


def test_by_step_returns_none_for_unknown_step():
    state = PlanExecutionState(plan_id="p1")
    assert state.by_step("unknown") is None


def test_slice_returns_only_requested_step_ids_in_original_order():
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("s1"))
    state.append(_entry("s2"))
    state.append(_entry("s3"))
    sliced = state.slice(["s3", "s1"])
    assert [e.step_id for e in sliced] == ["s1", "s3"]


def test_slice_of_empty_list_returns_empty():
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("s1"))
    assert state.slice([]) == []
