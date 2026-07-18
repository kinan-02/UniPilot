"""Per-step dispatch schemas (docs/agent/AGENT_VISION.md §7, §7.1, §7.2, §7.3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent_core.certainty import CertaintyTag, ToolInvocationRecord
from app.agent_core.planning.state import StateEntry


class StepInstructionFields(BaseModel):
    """The structured decision the orchestrator's step-prep pass produces --
    `prompt_builder` renders these into prose; they are also carried
    structured, as the anchor (§7.1's "one structured decision, two
    renderings" rule)."""

    goal: str
    description: str
    specific_instructions: list[str] = Field(default_factory=list)
    tone_language_notes: str = ""


class ReasoningParamsOverride(BaseModel):
    risk_level: Literal["low", "medium", "high"] | None = None
    min_iterations: int | None = None
    max_iterations: int | None = None
    temperature: float | None = None


class StepPrepOutput(BaseModel):
    """What the orchestrator's own step-prep reasoning call returns (§7)."""

    instruction_fields: StepInstructionFields
    context_requirements: list[str] = Field(default_factory=list)  # step_ids to pull -- usually == PlanStep.depends_on
    reasoning_params: ReasoningParamsOverride = Field(default_factory=ReasoningParamsOverride)
    output_schema_name: str
    output_schema: dict[str, Any]
    # Narrowing only (least-privilege per instance, §7.1) -- never widens the role's own ceiling.
    tool_grant_override: list[str] | None = None


class SubagentContextPackage(BaseModel):
    """What `context_builder` assembles (§7.2) -- a deliberately bounded package."""

    rendered_prompt: str  # prompt_builder's output
    structured_fields: StepInstructionFields  # same fields, structured -- the anchor
    dependency_state: list[StateEntry] = Field(default_factory=list)
    tool_grant: list[str] = Field(default_factory=list)  # role ceiling ∩ tool_grant_override
    output_schema_name: str
    output_schema: dict[str, Any]
    guardrails: list[str] = Field(default_factory=list)


class SubagentResult(BaseModel):
    """What a subagent returns (§7.3) -- never bare prose."""

    status: Literal["succeeded", "partial", "failed"]
    result: dict[str, Any] | None = None
    certainty: CertaintyTag
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)
    needs_another_round: bool = False


__all__ = [
    "StepInstructionFields",
    "ReasoningParamsOverride",
    "StepPrepOutput",
    "SubagentContextPackage",
    "SubagentResult",
]
