"""Unit tests for the Phase 6 `ExecutionGraph`."""

from __future__ import annotations

import pytest

from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.errors import (
    DependencyCycleError,
    DuplicateSubtaskIdError,
    UnknownDependencyError,
)
from app.agent.supervisor.graph import ExecutionGraph


def _subtask(subtask_id: str, *, depends_on: list[str] | None = None) -> PlannerSubtask:
    return PlannerSubtask(
        id=subtask_id,
        title=f"Subtask {subtask_id}",
        kind="analyze",
        capability_name="graduation_progress_workflow",
        objective="test",
        depends_on=depends_on or [],
    )


def test_unique_ids_accepted() -> None:
    graph = ExecutionGraph.build([_subtask("a"), _subtask("b")])
    assert graph.subtask_ids() == ["a", "b"]


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(DuplicateSubtaskIdError):
        ExecutionGraph.build([_subtask("a"), _subtask("a")])


def test_missing_dependency_rejected() -> None:
    with pytest.raises(UnknownDependencyError):
        ExecutionGraph.build([_subtask("a", depends_on=["does_not_exist"])])


def test_cycle_detected() -> None:
    with pytest.raises(DependencyCycleError):
        ExecutionGraph.build(
            [
                _subtask("a", depends_on=["b"]),
                _subtask("b", depends_on=["a"]),
            ]
        )


def test_self_dependency_is_a_cycle() -> None:
    with pytest.raises(DependencyCycleError):
        ExecutionGraph.build([_subtask("a", depends_on=["a"])])


def test_ready_subtasks_computed_correctly() -> None:
    graph = ExecutionGraph.build(
        [
            _subtask("a"),
            _subtask("b", depends_on=["a"]),
            _subtask("c", depends_on=["a"]),
        ]
    )
    assert graph.ready_subtasks(completed=set(), blocked=set()) == ["a"]
    assert graph.ready_subtasks(completed={"a"}, blocked=set()) == ["b", "c"]
    assert graph.ready_subtasks(completed={"a", "b"}, blocked=set()) == ["c"]
    assert graph.ready_subtasks(completed={"a", "b", "c"}, blocked=set()) == []


def test_ready_subtasks_excludes_blocked() -> None:
    graph = ExecutionGraph.build([_subtask("a"), _subtask("b")])
    assert graph.ready_subtasks(completed=set(), blocked={"a"}) == ["b"]


def test_linear_execution_order_correct() -> None:
    graph = ExecutionGraph.build(
        [
            _subtask("a"),
            _subtask("b", depends_on=["a"]),
            _subtask("c", depends_on=["b"]),
        ]
    )
    assert graph.topological_order() == ["a", "b", "c"]


def test_branch_execution_order_deterministic() -> None:
    # b and c both only depend on a and have no relative ordering constraint
    # -- declaration order must break the tie deterministically.
    graph = ExecutionGraph.build(
        [
            _subtask("a"),
            _subtask("b", depends_on=["a"]),
            _subtask("c", depends_on=["a"]),
            _subtask("d", depends_on=["b", "c"]),
        ]
    )
    order = graph.topological_order()
    assert order[0] == "a"
    assert order[-1] == "d"
    assert set(order[1:3]) == {"b", "c"}
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")

    # Running it again produces the exact same order (no hidden randomness).
    assert graph.topological_order() == order


def test_declaration_order_ties_are_broken_by_declaration_order() -> None:
    graph = ExecutionGraph.build([_subtask("z"), _subtask("y"), _subtask("x")])
    assert graph.topological_order() == ["z", "y", "x"]


def test_dependents_of_returns_expected_ids() -> None:
    graph = ExecutionGraph.build(
        [
            _subtask("a"),
            _subtask("b", depends_on=["a"]),
            _subtask("c", depends_on=["a"]),
        ]
    )
    assert set(graph.dependents_of("a")) == {"b", "c"}
    assert graph.dependents_of("b") == []


def test_dependents_skipped_when_parent_fails_is_supported_via_dependents_lookup() -> None:
    """The graph itself doesn't run anything -- it just exposes the lookup
    the runtime uses to skip dependents deterministically."""
    graph = ExecutionGraph.build(
        [
            _subtask("a"),
            _subtask("b", depends_on=["a"]),
        ]
    )
    failed = {"a"}
    dependents_of_failed = {dep for sid in failed for dep in graph.dependents_of(sid)}
    assert dependents_of_failed == {"b"}
