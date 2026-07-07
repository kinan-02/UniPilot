"""Typed errors raised by the Supervisor Orchestrator Runtime (Phase 6).

Every error here means "the plan/graph is structurally unusable" — the
runtime catches these at the boundary and turns them into a `status="failed"`
`SupervisorRunOutput` rather than letting them propagate. They are never
raised for a single subtask's *execution* failure — that's represented by
`SubtaskResult(status="failed")` instead.
"""

from __future__ import annotations


class SupervisorError(RuntimeError):
    """Base class for all supervisor runtime errors."""


class InvalidPlannerOutputError(SupervisorError):
    """Raised when `SupervisorRunInput.planner_output` can't be parsed as `PlannerOutput`."""


class DuplicateSubtaskIdError(SupervisorError):
    """Raised when the plan's subtasks contain a duplicate `id`."""


class UnknownDependencyError(SupervisorError):
    """Raised when a subtask's `depends_on` references an id not present in the plan."""


class DependencyCycleError(SupervisorError):
    """Raised when the subtask dependency graph contains a cycle."""
