"""Promotion readiness schemas (Phase 24)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PromotionReadinessLevel = Literal[
    "not_ready",
    "ready_for_shadow",
    "ready_for_limited_promotion",
    "ready_for_broader_promotion",
]

PromotionCandidateType = Literal[
    "workflow_promotion",
    "specialist_text_promotion",
    "synthesis_text_promotion",
    "planner_dynamic_specs",
    "dynamic_agent_execution",
    "clarification_user_facing",
    "plan_repair",
    "planner_first_live",
    "planner_first_live_proposal",
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


class PromotionCandidate(BaseModel):
    id: str
    type: PromotionCandidateType
    name: str
    description: str = ""
    required_suites: list[str] = Field(default_factory=list)
    allowed_scope: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class ReadinessThresholds(BaseModel):
    min_total_cases: int = 10
    min_pass_rate: float = 0.95
    min_candidate_case_count: int = 3

    require_zero_unsafe_failures: bool = True
    require_zero_student_write_failures: bool = True
    require_zero_action_proposal_failures: bool = True
    require_zero_raw_payload_leaks: bool = True
    require_zero_unexpected_promotions: bool = True

    min_unsafe_block_rate: float = 1.0
    min_promotion_precision: float = 1.0
    min_clarification_correctness: float = 0.9
    min_plan_repair_correctness: float = 0.9

    min_diverse_suite_count: int = 2


class PromotionReadinessDecision(BaseModel):
    candidate_id: str
    level: PromotionReadinessLevel
    passed: bool
    summary: str

    evaluated_suite_ids: list[str] = Field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate: float = 0.0

    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)
