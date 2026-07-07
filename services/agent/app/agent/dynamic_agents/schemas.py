"""Typed models for dynamically constructed sub-agents (Phase 15).

Dynamic agents are configuration — never generated code. An `AgentSpec`
describes what a sub-agent should do; `AgentBuilder` assembles a fixed block
sequence from `BlockLibrary`; `DynamicAgentInstance.run` executes that
sequence in shadow-only mode.

No field here may carry raw chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AgentReasoningPattern = Literal[
    "single_pass",
    "tool_observation_loop",
    "reflect_and_revise",
    "compare_and_synthesize",
    "structured_extraction",
    "clarification_assessment",
]

DynamicAgentRiskLevel = Literal["low", "medium", "high"]

BlockType = Literal[
    "context_filter",
    "reasoning",
    "observation_loop",
    "validation",
    "reflection",
    "synthesis",
    "summarization",
    "clarification_check",
]

DynamicAgentStatus = Literal[
    "completed",
    "needs_more_context",
    "unsupported",
    "failed",
    "skipped",
]

_FORBIDDEN_SPEC_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
)


class DynamicAgentBudget(BaseModel):
    max_reasoning_calls: int = 1
    max_tool_rounds: int = 0
    max_observations: int = 6
    max_validation_passes: int = 1
    max_runtime_ms: int = 30000


class DynamicAgentContextContract(BaseModel):
    allowed_context_sections: list[str] = Field(default_factory=list)
    required_context_sections: list[str] = Field(default_factory=list)
    forbidden_context_keys: list[str] = Field(default_factory=list)


class DynamicAgentValidationPolicy(BaseModel):
    require_sources: bool = False
    require_confidence: bool = True
    allow_missing_context: bool = True
    allow_proposed_actions: bool = False
    allow_writes: bool = False
    require_output_schema: bool = True
    max_output_chars: int = 6000


class AgentSpec(BaseModel):
    spec_id: str
    agent_name: str
    role: str
    objective: str
    reasoning_pattern: AgentReasoningPattern
    task_brief_id: str | None = None

    allowed_blocks: list[str] = Field(default_factory=list)
    allowed_observations: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)

    context_contract: DynamicAgentContextContract = Field(default_factory=DynamicAgentContextContract)
    expected_output_schema_name: str
    validation_policy: DynamicAgentValidationPolicy = Field(default_factory=DynamicAgentValidationPolicy)
    budget: DynamicAgentBudget = Field(default_factory=DynamicAgentBudget)

    boundaries: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risk_level: DynamicAgentRiskLevel = "medium"

    shadow_only: bool = True

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in value:
                if key in _FORBIDDEN_SPEC_FIELD_NAMES:
                    raise ValueError(f"forbidden_spec_field: {key}")
        return value


class TaskBrief(BaseModel):
    brief_id: str
    parent_plan_id: str | None = None
    parent_subtask_id: str | None = None

    objective: str
    user_goal: str
    local_instructions: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    relevant_context_summary: dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: dict[str, Any] = Field(default_factory=dict)
    expected_output_schema_name: str | None = None

    clarification_policy: dict[str, Any] = Field(default_factory=dict)


class BlockDescriptor(BaseModel):
    name: str
    block_type: BlockType
    description: str

    when_to_use: str
    when_not_to_use: str = ""

    required_inputs: list[str] = Field(default_factory=list)
    produced_outputs: list[str] = Field(default_factory=list)

    compatible_reasoning_patterns: list[AgentReasoningPattern] = Field(default_factory=list)

    read_only: bool = True
    side_effect_level: Literal["none", "proposal", "write", "unknown"] = "none"

    can_call_reasoning_block: bool = False
    can_use_observations: bool = False
    can_validate_output: bool = False
    can_synthesize: bool = False


class DynamicAgentRunInput(BaseModel):
    spec: AgentSpec
    task_brief: TaskBrief
    compiled_context: dict[str, Any] = Field(default_factory=dict)
    deterministic_observations: list[dict[str, Any]] = Field(default_factory=list)
    dependency_outputs: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class DynamicAgentRunOutput(BaseModel):
    status: DynamicAgentStatus
    spec_id: str
    agent_name: str
    result: dict[str, Any] = Field(default_factory=dict)
    decision_summary: str
    key_findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    proposed_actions: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("proposed_actions")
    @classmethod
    def _force_no_proposed_actions(cls, _value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return []


class AgentBuildResult(BaseModel):
    """Structured result when `AgentBuilder.build` fails validation."""

    success: bool
    instance: Any | None = None
    errors: list[str] = Field(default_factory=list)
