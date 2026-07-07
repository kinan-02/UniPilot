"""Cross-turn clarification state models (Phase 18)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ClarificationStateStatus = Literal[
    "pending",
    "answered",
    "assumed",
    "expired",
    "cancelled",
    "failed",
]

ClarificationResumeMode = Literal[
    "resume_original_request",
    "answer_only",
    "diagnostic_only",
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

_FORBIDDEN_COMPACT_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "compiled_context",
        "raw_context",
        "planner_output",
        "monitor_output",
        "workflow_response",
        "proposed_actions",
        "structured_blocks",
        "blocks",
        "evidence",
    }
)


def _reject_forbidden_fields(value: Any) -> Any:
    if isinstance(value, dict):
        for key in value:
            if key in _FORBIDDEN_FIELD_NAMES:
                raise ValueError(f"forbidden_clarification_state_field: {key}")
    return value


def sanitize_compact_context(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if lowered in _FORBIDDEN_COMPACT_CONTEXT_KEYS:
            continue
        if lowered in _FORBIDDEN_FIELD_NAMES:
            continue
        cleaned[key] = item
    return cleaned


class PendingClarificationState(BaseModel):
    clarification_id: str
    conversation_id: str
    user_id: str | None = None

    status: ClarificationStateStatus = "pending"

    original_user_message: str
    original_plan_id: str | None = None
    original_intent: str | None = None
    original_workflow_name: str | None = None

    questions: list[dict[str, Any]] = Field(default_factory=list)
    needs: list[dict[str, Any]] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    max_pending_turns: int = 3
    pending_turn_count: int = 0

    resume_mode: ClarificationResumeMode = "resume_original_request"

    compact_context: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        value = _reject_forbidden_fields(value)
        if isinstance(value, dict):
            compact = value.get("compact_context")
            if isinstance(compact, dict):
                value = {**value, "compact_context": sanitize_compact_context(compact)}
        return value


class ResolvedClarificationState(BaseModel):
    clarification_id: str
    conversation_id: str
    status: Literal["answered", "assumed", "expired", "cancelled"]
    answers: list[dict[str, Any]] = Field(default_factory=list)
    assumptions_created: list[dict[str, Any]] = Field(default_factory=list)
    resume_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _validate_no_forbidden_fields(cls, value: Any) -> Any:
        return _reject_forbidden_fields(value)
