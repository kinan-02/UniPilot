"""Execution graph utilities for the Supervisor Orchestrator Runtime (Phase 6).

Validates and orders `PlannerSubtask` dependencies. Purely deterministic —
no I/O, no LLM calls, no concurrency itself. `topological_order()` produces
a stable, dependency-respecting order for diagnostics/output ordering;
`ready_subtasks()` is what `supervisor.runtime` actually dispatches from,
one dependency "wave" (of concurrently runnable subtasks) at a time.
"""

from __future__ import annotations

from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.errors import (
    DependencyCycleError,
    DuplicateSubtaskIdError,
    UnknownDependencyError,
)


class ExecutionGraph:
    """A validated dependency graph over one plan's subtasks.

    Always construct via `ExecutionGraph.build(...)` — the plain
    constructor assumes the input has already been validated.
    """

    def __init__(self, subtasks: list[PlannerSubtask]) -> None:
        self._order: list[str] = [subtask.id for subtask in subtasks]
        self._by_id: dict[str, PlannerSubtask] = {subtask.id: subtask for subtask in subtasks}

    @classmethod
    def build(cls, subtasks: list[PlannerSubtask]) -> ExecutionGraph:
        """Validate `subtasks` and return a ready-to-use `ExecutionGraph`.

        Raises `DuplicateSubtaskIdError`, `UnknownDependencyError`, or
        `DependencyCycleError` for a structurally invalid plan — callers
        should treat any of these as "the plan cannot be executed", not as
        a single subtask's failure.
        """
        seen: set[str] = set()
        for subtask in subtasks:
            if subtask.id in seen:
                raise DuplicateSubtaskIdError(subtask.id)
            seen.add(subtask.id)

        for subtask in subtasks:
            for dependency in subtask.depends_on:
                if dependency not in seen:
                    raise UnknownDependencyError(f"{subtask.id} -> {dependency}")

        graph = cls(subtasks)
        if graph._has_cycle():
            raise DependencyCycleError("dependency cycle detected in planner output")
        return graph

    def subtask_ids(self) -> list[str]:
        """Subtask ids in original plan declaration order."""
        return list(self._order)

    def get(self, subtask_id: str) -> PlannerSubtask:
        return self._by_id[subtask_id]

    def dependencies_of(self, subtask_id: str) -> list[str]:
        return list(self._by_id[subtask_id].depends_on)

    def dependents_of(self, subtask_id: str) -> list[str]:
        return [other.id for other in self._by_id.values() if subtask_id in other.depends_on]

    def topological_order(self) -> list[str]:
        """Deterministic dependency-respecting execution order (Kahn's algorithm).

        Ties (multiple subtasks simultaneously ready) are broken by original
        plan declaration order, so branch execution order is stable rather
        than depending on set/dict iteration order.
        """
        in_degree = {subtask_id: len(self.dependencies_of(subtask_id)) for subtask_id in self._order}
        remaining = list(self._order)
        ordered: list[str] = []

        while remaining:
            ready = [subtask_id for subtask_id in remaining if in_degree[subtask_id] == 0]
            if not ready:
                # Unreachable when constructed via `build()` (cycles are
                # rejected up front) — defensive only.
                break
            next_id = ready[0]
            ordered.append(next_id)
            remaining.remove(next_id)
            for dependent_id in self.dependents_of(next_id):
                if dependent_id in in_degree:
                    in_degree[dependent_id] -= 1
        return ordered

    def ready_subtasks(self, *, completed: set[str], blocked: set[str]) -> list[str]:
        """Subtasks not yet completed/blocked whose dependencies are all completed."""
        ready = []
        for subtask_id in self._order:
            if subtask_id in completed or subtask_id in blocked:
                continue
            if set(self.dependencies_of(subtask_id)).issubset(completed):
                ready.append(subtask_id)
        return ready

    def _has_cycle(self) -> bool:
        """DFS-based cycle detection over the `id -> depends_on` adjacency."""
        unvisited, in_progress, done = 0, 1, 2
        state = dict.fromkeys(self._by_id, unvisited)

        def visit(node: str) -> bool:
            state[node] = in_progress
            for dependency in self.dependencies_of(node):
                if dependency not in state:
                    continue
                if state[dependency] == in_progress:
                    return True
                if state[dependency] == unvisited and visit(dependency):
                    return True
            state[node] = done
            return False

        return any(state[node] == unvisited and visit(node) for node in self._by_id)
