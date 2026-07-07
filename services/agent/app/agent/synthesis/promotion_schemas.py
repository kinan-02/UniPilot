"""Typed models for controlled synthesis text promotion (Phase 22)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SynthesisTextPromotionMode = Literal["off", "shadow_only", "promote_validated"]

SynthesisTextPromotionStatus = Literal["promoted", "blocked", "skipped", "failed"]

_FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
)


class SynthesisTextPromotionReason(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    details: dict[str, Any] = Field(default_factory=dict)


class SynthesisTextPromotionDecision(BaseModel):
    status: SynthesisTextPromotionStatus
    promoted: bool = False
    mode: SynthesisTextPromotionMode = "off"

    workflow_name: str | None = None
    synthesis_status: str | None = None

    reasons: list[SynthesisTextPromotionReason] = Field(default_factory=list)

    candidate_char_count: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    live_blocks_preserved: bool = True
    live_warnings_preserved: bool = True
    live_sources_preserved: bool = True
    live_actions_preserved: bool = True

    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            for key in values:
                if key in _FORBIDDEN_FIELD_NAMES:
                    raise ValueError(f"forbidden_field:{key}")
        return values
