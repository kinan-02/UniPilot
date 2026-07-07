"""Runtime readiness gate schemas (Phase 25)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RuntimeReadinessLevel = Literal[
    "not_ready",
    "ready_for_shadow",
    "ready_for_limited_promotion",
    "ready_for_broader_promotion",
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

LEVEL_ORDER: dict[RuntimeReadinessLevel, int] = {
    "not_ready": 0,
    "ready_for_shadow": 1,
    "ready_for_limited_promotion": 2,
    "ready_for_broader_promotion": 3,
}


def level_at_least(candidate: RuntimeReadinessLevel, required: RuntimeReadinessLevel) -> bool:
    return LEVEL_ORDER[candidate] >= LEVEL_ORDER[required]


def _reject_forbidden_fields(values: dict[str, Any]) -> dict[str, Any]:
    for key in values:
        if key in _FORBIDDEN_FIELD_NAMES:
            raise ValueError(f"forbidden_field:{key}")
    return values


class RuntimeReadinessCandidateApproval(BaseModel):
    candidate_id: str = Field(validation_alias="candidateId")
    level: RuntimeReadinessLevel
    approved: bool = False
    scope: list[str] = Field(default_factory=list)
    expires_at: datetime | None = Field(default=None, validation_alias="expiresAt")
    notes: str | None = None

    model_config = {"populate_by_name": True}


class RuntimeReadinessManifest(BaseModel):
    schema_version: str = Field(default="1", validation_alias="schemaVersion")
    generated_at: datetime | None = Field(default=None, validation_alias="generatedAt")
    reviewed_at: datetime | None = Field(default=None, validation_alias="reviewedAt")
    reviewed_by: str | None = Field(default=None, validation_alias="reviewedBy")
    source_report: str | None = Field(default=None, validation_alias="sourceReport")
    suite_run_id: str | None = Field(default=None, validation_alias="suiteRunId")
    candidates: list[RuntimeReadinessCandidateApproval] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class RuntimeReadinessGateInput(BaseModel):
    candidate_id: str
    requested_scope: str | None = None
    required_level: RuntimeReadinessLevel = "ready_for_limited_promotion"
    require_human_review: bool = True


class RuntimeReadinessGateDecision(BaseModel):
    allowed: bool = False
    candidate_id: str
    level: RuntimeReadinessLevel | None = None
    reasons: list[str] = Field(default_factory=list)
    reviewed: bool = False
    stale: bool = False
    scope_allowed: bool = False
