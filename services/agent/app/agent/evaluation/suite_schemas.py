"""Evaluation suite manifest schemas (Phase 24)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvalSuitePurpose = Literal[
    "core_regression",
    "read_only_promotion",
    "write_safety",
    "dynamic_agent_planning",
    "clarification",
    "plan_repair",
    "synthesis",
    "synthesis_promotion",
    "unsupported_requests",
    "raw_payload_safety",
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


class EvalSuiteManifest(BaseModel):
    id: str
    name: str
    purpose: EvalSuitePurpose
    description: str = ""

    case_ids: list[str] = Field(default_factory=list)
    tags_required: list[str] = Field(default_factory=list)
    tags_excluded: list[str] = Field(default_factory=list)

    minimum_case_count: int = 1
    required_for_candidates: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values
