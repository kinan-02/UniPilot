"""Typed models for plan monitoring (Phase 16).

The Monitor compares expected vs actual execution results and produces
diagnostic divergence signals and replan/repair recommendations. It never
calls an LLM and never changes live execution in Phase 16.

No field here may carry raw chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PlanAssumptionKind = Literal[
    "user_preference",
    "profile_fact",
    "academic_fact",
    "catalog_fact",
    "workflow_precondition",
    "tool_availability",
    "context_availability",
    "safety_constraint",
]

AssumptionProvenance = Literal[
    "confirmed",
    "assumed",
    "inferred",
    "deterministic",
    "llm_interpreted",
]

ExpectationKind = Literal[
    "status",
    "output_shape",
    "required_source",
    "required_block_type",
    "no_proposed_actions",
    "no_writes",
    "confidence_threshold",
    "missing_context_absent",
    "safe_match",
    "custom",
]

DivergenceKind = Literal[
    "none",
    "local_execution_failure",
    "assumption_violation",
    "goal_drift",
    "exhausted_path",
    "unsafe_output",
    "missing_context",
    "validation_failure",
    "promotion_blocked",
    "budget_exceeded",
]

ReplanAction = Literal[
    "continue",
    "local_retry",
    "local_substitute",
    "ask_clarification",
    "request_plan_repair",
    "request_plan_regeneration",
    "abort_safely",
]

MonitorStatus = Literal[
    "passed",
    "passed_with_warnings",
    "diverged",
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


class PlanAssumption(BaseModel):
    id: str
    kind: PlanAssumptionKind
    statement: str
    provenance: AssumptionProvenance
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    depends_on: list[str] = Field(default_factory=list)
    invalidation_signals: list[str] = Field(default_factory=list)
    consequence_if_wrong: Literal["low", "medium", "high"] = "medium"


class SubtaskExpectation(BaseModel):
    id: str
    subtask_id: str
    kind: ExpectationKind
    description: str
    expected_value: Any | None = None
    severity_if_failed: Literal["info", "warning", "error"] = "warning"


class MonitorInput(BaseModel):
    plan_id: str | None = None
    user_goal: str | None = None
    current_step_id: str | None = None

    planner_output: dict[str, Any] = Field(default_factory=dict)
    supervisor_output: dict[str, Any] = Field(default_factory=dict)
    subtask_records: list[dict[str, Any]] = Field(default_factory=list)

    assumptions: list[PlanAssumption] = Field(default_factory=list)
    expectations: list[SubtaskExpectation] = Field(default_factory=list)

    validation_metadata: dict[str, Any] = Field(default_factory=dict)
    promotion_metadata: dict[str, Any] = Field(default_factory=dict)
    specialist_validation_metadata: dict[str, Any] = Field(default_factory=dict)
    dynamic_agent_metadata: dict[str, Any] = Field(default_factory=dict)
    task_understanding: dict[str, Any] = Field(default_factory=dict)

    conversation_assumptions: list[str] = Field(default_factory=list)
    latest_user_message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in value:
                if key in _FORBIDDEN_FIELD_NAMES:
                    raise ValueError(f"forbidden_monitor_field: {key}")
        return value


class DivergenceSignal(BaseModel):
    kind: DivergenceKind
    severity: Literal["info", "warning", "error"]
    message: str
    related_assumption_ids: list[str] = Field(default_factory=list)
    related_subtask_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReplanDecision(BaseModel):
    action: ReplanAction
    reason: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    divergence_kinds: list[DivergenceKind] = Field(default_factory=list)
    affected_subtasks: list[str] = Field(default_factory=list)
    affected_assumptions: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    repair_scope: Literal["none", "current_step", "remaining_plan", "entire_plan"] = "none"


class MonitorOutput(BaseModel):
    status: MonitorStatus
    plan_id: str | None = None
    signals: list[DivergenceSignal] = Field(default_factory=list)
    decision: ReplanDecision
    checked_assumption_count: int = 0
    checked_expectation_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
