"""Unit tests for `app.agent_core.planning.state` (docs/agent/AGENT_VISION.md §3.2, §8)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.planning.schemas import PlanGraph
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


def test_merge_plan_graph_unions_forward_edges():
    state = PlanExecutionState(plan_id="p1")
    state.merge_plan_graph(PlanGraph(forward={"1a": []}, dependents={"1a": []}, execution_layers=[["1a"]]))
    state.merge_plan_graph(PlanGraph(forward={"2a": ["1a"]}, dependents={"1a": ["2a"], "2a": []}, execution_layers=[["2a"]]))
    assert state.plan_graph.forward == {"1a": [], "2a": ["1a"]}


def test_merge_plan_graph_grows_a_prior_steps_dependents_list():
    """A later invocation's new step depending on an earlier invocation's
    step must extend that earlier step's `dependents` list, not just add a
    fresh entry under the new step's own id (PLANNER_OUTPUT_DESIGN.md §5)."""
    state = PlanExecutionState(plan_id="p1")
    state.merge_plan_graph(PlanGraph(forward={"1a": []}, dependents={"1a": []}, execution_layers=[["1a"]]))
    state.merge_plan_graph(PlanGraph(forward={"2a": ["1a"]}, dependents={"1a": ["2a"], "2a": []}, execution_layers=[["2a"]]))
    assert state.plan_graph.dependents["1a"] == ["2a"]


def test_merge_plan_graph_does_not_duplicate_a_dependent_seen_twice():
    state = PlanExecutionState(plan_id="p1")
    state.merge_plan_graph(PlanGraph(forward={"1a": []}, dependents={"1a": ["1b"]}))
    state.merge_plan_graph(PlanGraph(forward={}, dependents={"1a": ["1b"]}))
    assert state.plan_graph.dependents["1a"] == ["1b"]


def test_merge_plan_graph_appends_execution_layers_across_invocations():
    state = PlanExecutionState(plan_id="p1")
    state.merge_plan_graph(PlanGraph(execution_layers=[["1a", "1b"], ["1c"]]))
    state.merge_plan_graph(PlanGraph(execution_layers=[["2a"]]))
    assert state.plan_graph.execution_layers == [["1a", "1b"], ["1c"], ["2a"]]
