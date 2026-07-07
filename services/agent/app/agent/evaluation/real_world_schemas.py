"""Real-world eval case import schemas (Phase 26)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RealWorldCaseSource = Literal[
    "manual",
    "dogfooding",
    "support_log",
    "student_interview",
    "developer_collected",
]

_FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "raw_transcript",
        "transcript_rows",
        "full_transcript_rows",
        "conversation_history",
        "raw_conversation",
        "raw_context",
        "raw_prompt",
        "raw_response",
        "catalog_dump",
        "raw_pdf_bytes",
        "pdf_bytes",
        "proposed_action_payload",
    }
)

_FORBIDDEN_IMPORT_KEYS: frozenset[str] = frozenset(
    {
        "raw_transcript",
        "transcript_rows",
        "full_transcript_rows",
        "conversation_history",
        "raw_conversation",
        "raw_context",
        "raw_context_dump",
        "original_user_message",
        "original_message",
        "private_message",
        "student_id",
        "national_id",
        "email",
        "phone",
        "full_name",
        "student_name",
        "pdf_path",
        "file_path",
        "uploaded_file",
        "raw_pdf",
        "raw_pdf_bytes",
    }
)


def _reject_forbidden_fields(values: dict[str, Any]) -> dict[str, Any]:
    for key in values:
        lowered = str(key).lower()
        if key in _FORBIDDEN_FIELD_NAMES or lowered in _FORBIDDEN_IMPORT_KEYS:
            raise ValueError(f"forbidden_field:{key}")
    return values


class RealWorldCaseInput(BaseModel):
    """Anonymized real-world case payload for import into offline eval fixtures."""

    source: RealWorldCaseSource = "manual"
    original_language: str | None = None

    anonymized_user_message: str
    anonymized_context: dict[str, Any] = Field(default_factory=dict)

    expected_behavior_notes: str | None = None
    reviewer_expected_outcome: dict[str, Any] = Field(default_factory=dict)

    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _forbid_unsafe_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values

    @model_validator(mode="after")
    def _require_anonymized_message(self) -> RealWorldCaseInput:
        if not (self.anonymized_user_message or "").strip():
            raise ValueError("anonymized_user_message_required")
        return self


def assert_no_forbidden_import_keys(payload: dict[str, Any]) -> None:
    """Reject obvious raw/private import keys at the top level and nested."""
    violations: list[str] = []

    def _walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_str = str(key)
                lowered = key_str.lower()
                if key_str in _FORBIDDEN_IMPORT_KEYS or lowered in _FORBIDDEN_IMPORT_KEYS:
                    violations.append(f"{path}.{key_str}" if path else key_str)
                _walk(nested, f"{path}.{key_str}" if path else key_str)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk(item, f"{path}[{index}]")

    _walk(payload, "")
    if violations:
        joined = ", ".join(violations[:20])
        raise ValueError(f"forbidden_import_keys:{joined}")
