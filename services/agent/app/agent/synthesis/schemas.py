"""Typed models for synthesis / final answer composition (Phase 21)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvidenceSourceType = Literal[
    "deterministic_workflow",
    "internal_api",
    "catalog_rule",
    "degree_requirement",
    "confirmed_user_clarification",
    "assumed_user_preference",
    "specialist_agent",
    "dynamic_agent",
    "monitor",
    "plan_repair",
    "planner",
    "unknown",
]

EvidenceTrustLevel = Literal[
    "authoritative",
    "high",
    "medium",
    "low",
    "untrusted",
]

ConflictSeverity = Literal["info", "warning", "error"]

SynthesisRequestedNextStep = Literal[
    "none",
    "retrieve_more_context",
    "ask_clarification",
    "replan",
]

SynthesisStatus = Literal[
    "candidate_ready",
    "candidate_ready_with_warnings",
    "needs_clarification",
    "insufficient_evidence",
    "unsafe",
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


class EvidenceItem(BaseModel):
    id: str
    source_type: EvidenceSourceType
    source_name: str
    claim: str
    trust_level: EvidenceTrustLevel
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    provenance: Literal[
        "deterministic",
        "confirmed",
        "assumed",
        "llm_generated",
        "diagnostic",
        "unknown",
    ] = "unknown"
    supports_final_answer: bool = True
    related_subtask_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class SynthesisConflict(BaseModel):
    id: str
    severity: ConflictSeverity
    summary: str
    evidence_item_ids: list[str] = Field(default_factory=list)
    resolution: Literal[
        "prefer_authoritative",
        "prefer_confirmed",
        "surface_uncertainty",
        "exclude_low_trust",
        "requires_clarification",
        "unresolved",
    ] = "unresolved"


class SynthesisInput(BaseModel):
    synthesis_id: str
    user_goal: str | None = None
    normalized_request: str | None = None

    live_response_summary: dict[str, Any] = Field(default_factory=dict)
    workflow_summary: dict[str, Any] = Field(default_factory=dict)
    specialist_summaries: list[dict[str, Any]] = Field(default_factory=list)
    dynamic_agent_summaries: list[dict[str, Any]] = Field(default_factory=list)

    monitor_summary: dict[str, Any] = Field(default_factory=dict)
    clarification_summary: dict[str, Any] = Field(default_factory=dict)
    plan_repair_summary: dict[str, Any] = Field(default_factory=dict)
    planner_dynamic_agents_summary: dict[str, Any] = Field(default_factory=dict)

    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class SynthesisOutput(BaseModel):
    status: SynthesisStatus
    synthesis_id: str

    candidate_answer_text: str | None = None
    decision_summary: str
    key_points: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    conflicts: list[SynthesisConflict] = Field(default_factory=list)

    evidence_used_ids: list[str] = Field(default_factory=list)
    evidence_excluded_ids: list[str] = Field(default_factory=list)

    safe_to_show: bool = False
    safe_to_promote: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    requested_next_step: SynthesisRequestedNextStep | None = None

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values
