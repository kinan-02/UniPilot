"""Typed models for clarification capability (Phase 17).

Clarification represents uncertainty that may warrant user attention.
Phase 17 is diagnostic-only by default — no LLM calls, no writes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ClarificationAmbiguityType = Literal[
    "preference",
    "epistemic",
    "mixed",
    "unknown",
]

ClarificationConsequence = Literal[
    "low",
    "medium",
    "high",
]

ClarificationSource = Literal[
    "monitor",
    "planner",
    "orchestrator",
    "specialist",
    "dynamic_agent",
    "workflow",
    "manual",
]

ClarificationAction = Literal[
    "ask_user",
    "assume_default",
    "resolve_epistemically",
    "skip",
]

ClarificationProvenance = Literal[
    "confirmed",
    "assumed",
]

ClarificationCapabilityStatus = Literal[
    "question_ready",
    "assumed_default",
    "resolved_epistemically",
    "skipped",
    "failed",
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


def _reject_forbidden_fields(value: Any) -> Any:
    if isinstance(value, dict):
        for key in value:
            if key in _FORBIDDEN_FIELD_NAMES:
                raise ValueError(f"forbidden_clarification_field: {key}")
    return value


class ClarificationNeed(BaseModel):
    id: str
    source: ClarificationSource
    ambiguity_type: ClarificationAmbiguityType
    consequence: ClarificationConsequence
    question_topic: str
    reason: str
    options: list[str] = Field(default_factory=list)
    default_assumption: str | None = None
    affected_plan_id: str | None = None
    affected_subtask_ids: list[str] = Field(default_factory=list)
    related_assumption_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)


class ClarificationDecision(BaseModel):
    need_id: str
    action: ClarificationAction
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    selected_default: str | None = None
    should_batch: bool = True

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)


class ClarificationQuestion(BaseModel):
    id: str
    need_id: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True
    consequence: ClarificationConsequence
    ambiguity_type: ClarificationAmbiguityType

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)


class ClarificationAnswer(BaseModel):
    need_id: str
    value: str
    provenance: ClarificationProvenance
    source: Literal["user", "fallback", "system_default"]
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)


class ClarificationCapabilityOutput(BaseModel):
    status: ClarificationCapabilityStatus
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    answers: list[ClarificationAnswer] = Field(default_factory=list)
    assumptions_created: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)
