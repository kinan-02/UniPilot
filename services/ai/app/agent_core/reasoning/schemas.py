"""Typed models for the shared LLM reasoning runtime (Phase 1 foundation).

These models define the public contract for `ReasoningBlock`. Only structured,
machine-readable summaries ever leave this module — raw chain-of-thought text
is never captured in any model here or persisted anywhere.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ReasoningRiskLevel = Literal["low", "medium", "high"]
ReasoningStatus = Literal["completed", "needs_tool", "needs_more_context", "failed"]

# Status of a single internal reasoning pass. "ok" means the pass finished
# normally (either an intermediate checkpoint or, on the last pass, a
# candidate final result); the other two allow any pass to short-circuit the
# loop early.
ReasoningPassStatus = Literal["ok", "needs_tool", "needs_more_context"]


class ReasoningToolSpec(BaseModel):
    """Describes a tool the reasoning pass is allowed to request (not executed here)."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


class ReasoningToolRequest(BaseModel):
    """A tool invocation the reasoning pass would like performed by the caller."""

    tool_name: str
    purpose: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ReasoningBlockInput(BaseModel):
    """Everything a `ReasoningBlock.run` call needs for one reasoning task."""

    block_id: str
    agent_name: str
    objective: str
    task_context: dict[str, Any] = Field(default_factory=dict)
    available_tools: list[ReasoningToolSpec] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    output_schema_name: str
    output_schema: dict[str, Any]
    risk_level: ReasoningRiskLevel = "medium"
    min_reasoning_iterations: int | None = None
    max_reasoning_iterations: int | None = None
    max_schema_repair_attempts: int = 2
    temperature: float | None = None
    # Per-call ceiling passed straight through to `LLMAdapter.complete_json`.
    # Without this, every pass (and every schema-repair attempt) fell through
    # to the underlying OpenAI SDK's own 600s default -- a real live smoke
    # test found a turn hang for 8+ minutes with no ceiling in effect at all,
    # traced back to this field not existing on this input at the time.
    timeout: float | None = None
    # Which `PromptRegistry` contract to use for the reasoning-pass system prompt.
    # Defaults to the generic Phase 1 contract when omitted, so Phase 1 callers
    # (and tests) are unaffected. Phase 2+ role-specific callers set this to
    # their own contract name (e.g. `intent_classifier_v1`).
    prompt_contract_name: str | None = None


class ReasoningBlockOutput(BaseModel):
    """Structured result returned by `ReasoningBlock.run`.

    `result` (when present) is validated against the task-specific
    `ReasoningBlockInput.output_schema` — never against this model itself.
    """

    status: ReasoningStatus
    result: dict[str, Any] | None = None
    tool_requests: list[ReasoningToolRequest] = Field(default_factory=list)
    decision_summary: str
    key_factors: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    schema_valid: bool
    iterations_used: int
    repair_attempts_used: int


class ReasoningPassPayload(BaseModel):
    """Lenient, machine-readable summary of a single reasoning pass.

    This is the internal shape every LLM call in the loop is asked to return.
    It intentionally has no field for raw/private reasoning text — only a
    short `summary` plus structured extras.
    """

    status: ReasoningPassStatus = "ok"
    summary: str = ""
    key_factors: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_requests: list[ReasoningToolRequest] = Field(default_factory=list)
    confidence: float | None = None
    result: dict[str, Any] | None = None


class SchemaValidationResult(BaseModel):
    """Outcome of validating a `result` dict against a JSON schema."""

    valid: bool
    errors: list[str] = Field(default_factory=list)


class SchemaRepairOutcome(BaseModel):
    """Outcome of running the schema repair loop."""

    result: dict[str, Any] | None
    valid: bool
    errors: list[str] = Field(default_factory=list)
    attempts_used: int


class ReasoningTrace(BaseModel):
    """Developer-facing trace summary. Never includes raw prompts or chain-of-thought."""

    block_id: str
    agent_name: str
    objective: str
    iterations_used: int
    repair_attempts_used: int
    status: ReasoningStatus
    schema_valid: bool
    decision_summary: str
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float
