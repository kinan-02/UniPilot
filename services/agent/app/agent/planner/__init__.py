"""Planner Agent (Phase 5).

Converts a `TaskUnderstandingOutput` into a structured, capability-aware
execution plan (subtasks, dependencies, required context, success criteria)
via the shared `ReasoningBlock` runtime, consulting the Phase 4
`CapabilityRegistry` and `ContextCompiler`. Diagnostic/dry-run only —
nothing here executes a subtask or changes live workflow selection.
Importing this package has no side effects.
"""

from __future__ import annotations

from app.agent.planner.agent import build_execution_plan
from app.agent.planner.legacy_mapping import (
    build_legacy_workflow_plan_summary,
    legacy_workflow_to_capability_name,
)
from app.agent.planner.schemas import (
    PlannerAutonomyLevel,
    PlannerExecutionMode,
    PlannerInput,
    PlannerOutput,
    PlannerRiskLevel,
    PlannerSource,
    PlannerStatus,
    PlannerSubtask,
    PlannerWriteRisk,
    SubtaskKind,
)

__all__ = [
    "build_execution_plan",
    "build_legacy_workflow_plan_summary",
    "legacy_workflow_to_capability_name",
    "PlannerAutonomyLevel",
    "PlannerExecutionMode",
    "PlannerInput",
    "PlannerOutput",
    "PlannerRiskLevel",
    "PlannerSource",
    "PlannerStatus",
    "PlannerSubtask",
    "PlannerWriteRisk",
    "SubtaskKind",
]
