"""Typed models for warm planner repair (Phase 19).

Diagnostic-only by default. No chain-of-thought or raw context payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PlanDeltaSource = Literal[
    "monitor",
    "clarification",
    "supervisor",
    "dynamic_agent",
    "specialist",
    "workflow",
    "user_message",
]

PlanDeltaKind = Literal[
    "clarification_answered",
    "assumption_violated",
    "goal_drift",
    "missing_context_resolved",
    "missing_context_unresolved",
    "subtask_failed",
    "exhausted_path",
    "validation_failed",
    "unsafe_output_detected",
    "budget_exceeded",
    "user_goal_changed",
]

RepairMode = Literal[
    "repair",
    "regenerate",
    "continue",
    "clarify_first",
    "abort_safely",
]

PlanRepairStatus = Literal[
    "repaired",
    "regenerated",
    "continued",
    "clarification_needed",
    "aborted_safely",
    "failed",
    "skipped",
]

_FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
)


def _reject_forbidden_fields(values: dict[str, Any]) -> dict[str, Any]:
    for key in values:
        if key in _FORBIDDEN_FIELD_NAMES:
            raise ValueError(f"forbidden_field:{key}")
    return values


class PlanSnapshot(BaseModel):
    plan_id: str
    user_goal: str
    normalized_request: str | None = None
    planner_mode: Literal["cold", "warm"] = "cold"

    subtasks: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    replan_triggers: list[str] = Field(default_factory=list)

    created_at: datetime | None = None
    source: Literal["planner_output", "fallback", "manual", "unknown"] = "unknown"

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class PlanExecutionDelta(BaseModel):
    delta_id: str
    source: PlanDeltaSource
    kind: PlanDeltaKind
    summary: str

    affected_subtask_ids: list[str] = Field(default_factory=list)
    affected_assumption_ids: list[str] = Field(default_factory=list)

    confirmed_answers: list[dict[str, Any]] = Field(default_factory=list)
    assumptions_created: list[dict[str, Any]] = Field(default_factory=list)
    monitor_signals: list[dict[str, Any]] = Field(default_factory=list)

    evidence: dict[str, Any] = Field(default_factory=dict)
    consequence: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class PlanRepairRequest(BaseModel):
    request_id: str
    prior_plan: PlanSnapshot | None = None
    user_goal: str
    original_user_message: str | None = None
    current_user_message: str | None = None

    deltas: list[PlanExecutionDelta] = Field(default_factory=list)
    monitor_decision: dict[str, Any] = Field(default_factory=dict)
    confirmed_clarifications: list[dict[str, Any]] = Field(default_factory=list)

    requested_mode: RepairMode | None = None
    dry_run: bool = True

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class PlanRepairOutput(BaseModel):
    status: PlanRepairStatus
    mode_used: RepairMode
    plan_id: str | None = None

    repaired_plan: dict[str, Any] | None = None
    preserved_subtask_ids: list[str] = Field(default_factory=list)
    revised_subtask_ids: list[str] = Field(default_factory=list)
    removed_subtask_ids: list[str] = Field(default_factory=list)
    added_subtask_ids: list[str] = Field(default_factory=list)

    decision_summary: str
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    safe_to_use: bool = False

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values
