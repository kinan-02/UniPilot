"""Unit tests for `app.agent_core.planning.rewrite`
(docs/agent/PLANNER_OUTPUT_DESIGN.md §4, §5)."""

from __future__ import annotations

from app.agent_core.planning.rewrite import check_hollow_result, compute_plan_graph, rewrite_step_ids
from app.agent_core.planning.schemas import PlanStep, PlanStepDraft


def _draft(step_id: str, depends_on: list[str] | None = None, objective: str = "o") -> PlanStepDraft:
    return PlanStepDraft(step_id=step_id, objective=objective, depends_on=depends_on or [])


# -- rewrite_step_ids -------------------------------------------------------


def test_rewrite_step_ids_produces_globally_unique_ids_from_local_labels():
    steps = rewrite_step_ids([_draft("A"), _draft("B")], invocation=1, known_global_ids=set())
    assert [s.step_id for s in steps] == ["1a", "1b"]


def test_rewrite_step_ids_translates_a_same_batch_local_label_dependency():
    steps = rewrite_step_ids([_draft("A"), _draft("B", depends_on=["A"])], invocation=1, known_global_ids=set())
    by_id = {s.step_id: s for s in steps}
    assert by_id["1b"].depends_on == ["1a"]


def test_rewrite_step_ids_leaves_an_already_global_dependency_as_is():
    steps = rewrite_step_ids([_draft("A", depends_on=["1x"])], invocation=2, known_global_ids={"1x"})
    assert steps[0].depends_on == ["1x"]


def test_rewrite_step_ids_drops_a_dangling_dependency():
    steps = rewrite_step_ids([_draft("A", depends_on=["nonexistent"])], invocation=1, known_global_ids=set())
    assert steps[0].depends_on == []


def test_rewrite_step_ids_dedupes_repeated_dependency_entries():
    steps = rewrite_step_ids(
        [_draft("A"), _draft("B", depends_on=["A", "A"])], invocation=1, known_global_ids=set()
    )
    by_id = {s.step_id: s for s in steps}
    assert by_id["1b"].depends_on == ["1a"]


def test_rewrite_step_ids_disambiguates_case_variant_label_collision():
    # "A" and "a" both lower() to the same global id -- must not silently
    # collapse into one step.
    steps = rewrite_step_ids([_draft("A"), _draft("a")], invocation=1, known_global_ids=set())
    step_ids = [s.step_id for s in steps]
    assert len(step_ids) == len(set(step_ids)) == 2


def test_rewrite_step_ids_disambiguates_reused_local_label():
    # The model reusing the exact same local label for two different drafts
    # -- must still produce two distinct final steps, not one.
    steps = rewrite_step_ids(
        [_draft("A", objective="first"), _draft("A", objective="second")], invocation=1, known_global_ids=set()
    )
    step_ids = [s.step_id for s in steps]
    assert len(step_ids) == len(set(step_ids)) == 2
    assert {s.objective for s in steps} == {"first", "second"}


def test_rewrite_step_ids_breaks_a_same_batch_cycle():
    steps = rewrite_step_ids(
        [_draft("A", depends_on=["B"]), _draft("B", depends_on=["A"])],
        invocation=1,
        known_global_ids=set(),
    )
    by_id = {s.step_id: s for s in steps}
    # One of the two back-edges must be dropped -- a genuine cycle can't survive.
    assert not (by_id["1a"].depends_on == ["1b"] and by_id["1b"].depends_on == ["1a"])


def test_rewrite_step_ids_breaks_a_self_referencing_dependency():
    steps = rewrite_step_ids([_draft("A", depends_on=["A"])], invocation=1, known_global_ids=set())
    assert steps[0].depends_on == []


# -- check_hollow_result ------------------------------------------------------


def test_hollow_in_progress_with_no_steps():
    assert check_hollow_result("in_progress", [], None) is True


def test_not_hollow_in_progress_with_steps():
    steps = rewrite_step_ids([_draft("A")], invocation=1, known_global_ids=set())
    assert check_hollow_result("in_progress", steps, None) is False


def test_hollow_blocked_with_no_clarification_question():
    assert check_hollow_result("blocked_needs_clarification", [], None) is True


def test_not_hollow_blocked_with_a_clarification_question():
    assert check_hollow_result("blocked_needs_clarification", [], "What did you mean?") is False


def test_not_hollow_complete_with_no_steps():
    # "complete" legitimately ends with no new steps -- the plan is just done.
    assert check_hollow_result("complete", [], None) is False


# -- compute_plan_graph -------------------------------------------------------


def test_compute_plan_graph_matches_the_worked_example():
    """PLANNER_OUTPUT_DESIGN.md §7's invocation-1 worked example: four
    independent steps (1a-1d) followed by two steps (1e, 1f) each depending
    on a subset of them -- must produce exactly the documented graph."""
    drafts = [
        _draft("A"),
        _draft("B"),
        _draft("C"),
        _draft("D"),
        _draft("E", depends_on=["A", "B"]),
        _draft("F", depends_on=["A"]),
    ]
    steps = rewrite_step_ids(drafts, invocation=1, known_global_ids=set())
    graph = compute_plan_graph(steps)

    assert graph.forward == {
        "1a": [],
        "1b": [],
        "1c": [],
        "1d": [],
        "1e": ["1a", "1b"],
        "1f": ["1a"],
    }
    assert graph.dependents == {
        "1a": ["1e", "1f"],
        "1b": ["1e"],
        "1c": [],
        "1d": [],
        "1e": [],
        "1f": [],
    }
    assert graph.execution_layers == [["1a", "1b", "1c", "1d"], ["1e", "1f"]]


def test_compute_plan_graph_dependents_includes_edges_pointing_outside_the_batch():
    """A new step depending on an already-completed prior-invocation step
    must still show up in that step's `dependents` in the delta, even
    though the prior step isn't itself a key in `forward` (it's not part of
    this batch) -- this is what `PlanExecutionState.merge_plan_graph` relies
    on to grow the prior step's dependents list."""
    step = PlanStep(step_id="2a", objective="o", depends_on=["1a"])
    graph = compute_plan_graph([step])
    assert graph.dependents == {"1a": ["2a"], "2a": []}
    assert "1a" not in graph.forward
