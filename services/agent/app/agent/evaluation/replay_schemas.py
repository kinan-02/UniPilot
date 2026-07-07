"""Offline replay / evaluation harness schemas (Phase 23)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvalCaseKind = Literal[
    "graduation_progress",
    "course_question",
    "requirement_explanation",
    "semester_planning",
    "transcript_import",
    "profile_update",
    "ambiguous_preference",
    "missing_context",
    "unsafe_write_attempt",
    "dynamic_agent_planning",
    "clarification_cross_turn",
    "plan_repair",
    "synthesis_promotion",
    "unsupported_request",
]

ExpectedOutcomeStatus = Literal["passed", "blocked", "skipped", "promoted", "not_applicable"]

EvalMode = Literal["gates_only", "shadow_replay", "full_llm_shadow_replay"]

_FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "raw_context",
        "raw_prompt",
        "raw_response",
        "full_transcript_rows",
        "catalog_dump",
        "raw_blocks",
        "proposed_action_payload",
    }
)


def _reject_forbidden_fields(values: dict[str, Any]) -> dict[str, Any]:
    for key in values:
        if key in _FORBIDDEN_FIELD_NAMES:
            raise ValueError(f"forbidden_field:{key}")
    return values


class EvalExpectedOutcome(BaseModel):
    expected_intent: str | None = None
    expected_workflow: str | None = None
    expected_capabilities: list[str] = Field(default_factory=list)

    expected_dynamic_spec_count: int | None = None
    expected_dynamic_spec_statuses: list[str] = Field(default_factory=list)

    expected_monitor_signals: list[str] = Field(default_factory=list)
    expected_clarification_action: str | None = None
    expected_plan_repair_mode: str | None = None

    expected_synthesis_status: str | None = None
    expected_synthesis_promotion: ExpectedOutcomeStatus = "not_applicable"

    expected_workflow_promotion: ExpectedOutcomeStatus = "not_applicable"
    expected_specialist_text_promotion: ExpectedOutcomeStatus = "not_applicable"

    expected_required_reason_codes: list[str] = Field(default_factory=list)
    forbidden_reason_codes: list[str] = Field(default_factory=list)

    must_not_create_proposed_actions: bool = True
    must_not_write_student_data: bool = True
    must_not_change_blocks: bool = True
    must_not_change_sources: bool = True

    expected_oracle_facts: dict[str, Any] = Field(default_factory=dict)
    forbidden_claims: list[str] = Field(default_factory=list)


class MockReasoningOutput(BaseModel):
    contract_name: str
    output: dict[str, Any]
    call_index: int | None = None


class EvalCase(BaseModel):
    id: str
    name: str
    kind: EvalCaseKind
    description: str = ""

    user_message: str
    locale: str | None = None

    synthetic_world: dict[str, Any] = Field(default_factory=dict)
    compact_context: dict[str, Any] = Field(default_factory=dict)

    live_response_summary: dict[str, Any] = Field(default_factory=dict)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)

    mock_reasoning_outputs: list[MockReasoningOutput] = Field(default_factory=list)

    expected: EvalExpectedOutcome = Field(default_factory=EvalExpectedOutcome)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _forbid_cot_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _reject_forbidden_fields(values)
        return values


class EvalGateResult(BaseModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    reason_codes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvalCaseResult(BaseModel):
    case_id: str
    name: str
    status: Literal["passed", "failed", "error"]
    gates: list[EvalGateResult] = Field(default_factory=list)

    actual_intent: str | None = None
    actual_workflow: str | None = None

    actual_monitor_signals: list[str] = Field(default_factory=list)
    actual_clarification_action: str | None = None
    actual_plan_repair_mode: str | None = None

    actual_synthesis_status: str | None = None
    actual_synthesis_promotion: str | None = None

    oracle_failures: list[str] = Field(default_factory=list)
    safety_failures: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    reasoning_call_summaries: list[dict[str, Any]] = Field(default_factory=list)
    side_effect_violations: list[dict[str, str]] = Field(default_factory=list)
    full_shadow: dict[str, Any] = Field(default_factory=dict)


class EvalRunSummary(BaseModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    errored_cases: int
    pass_rate: float

    intent_accuracy: float | None = None
    workflow_accuracy: float | None = None

    dynamic_specs_expected: int = 0
    dynamic_specs_validated: int = 0
    dynamic_specs_rejected: int = 0

    clarification_questions_expected: int = 0
    clarification_questions_correct: int = 0

    plan_repair_expected: int = 0
    plan_repair_correct: int = 0

    synthesis_candidates: int = 0
    synthesis_promotions: int = 0
    synthesis_blocks: int = 0

    unsafe_cases_blocked: int = 0
    proposed_action_failures: int = 0
    student_write_failures: int = 0
    raw_payload_leak_failures: int = 0
