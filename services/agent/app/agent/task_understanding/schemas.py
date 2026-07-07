"""Typed models for the Task Understanding Agent (Phase 3).

`TaskUnderstandingAgent` produces a richer, structured understanding of a
student's request than the rules-first intent classifier — it is diagnostic
output for future planning phases, not a production routing decision. As
with the shared reasoning runtime, no field here may carry raw
chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskUnderstandingStatus = Literal["completed", "needs_more_context", "failed"]

TaskCategory = Literal[
    "simple_question",
    "academic_analysis",
    "planning",
    "transcript_processing",
    "requirement_explanation",
    "write_or_update_request",
    "multi_step_task",
    "unsupported",
]

TaskComplexity = Literal["low", "medium", "high"]

# 0 — deterministic direct answer only
# 1 — LLM explanation over deterministic result
# 2 — task understanding + deterministic workflow
# 3 — planner needed
# 4 — multi-agent/specialist execution likely needed
# 5 — write/action proposal likely required
#
# Phase 3: these are recommendations only and do not change routing behavior.
AutonomyLevel = Literal[0, 1, 2, 3, 4, 5]

AUTONOMY_LEVEL_DESCRIPTIONS: dict[int, str] = {
    0: "deterministic direct answer only",
    1: "LLM explanation over deterministic result",
    2: "task understanding + deterministic workflow",
    3: "planner needed",
    4: "multi-agent/specialist execution likely needed",
    5: "write/action proposal likely required",
}

SuggestedNextLayer = Literal[
    "deterministic_workflow",
    "planner",
    "clarification",
    "unsupported",
]

WriteRisk = Literal["none", "possible", "explicit"]

TaskUnderstandingSource = Literal[
    "llm_reasoning_block",
    "deterministic_fallback",
    "hybrid",
]


class TaskUnderstandingInput(BaseModel):
    """Minimal, task-specific context for one `understand_user_task` call.

    Deliberately excludes large context (full catalog, transcript rows,
    degree requirements, wiki snippets, raw Mongo documents) — the agent
    understands the task, it does not solve it.
    """

    user_message: str
    conversation_summary: str | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    existing_entities: dict[str, Any] = Field(default_factory=dict)
    # `list[str]` (not `dict`) to match how assumptions are represented
    # elsewhere in the project (`AgentContextPack.assumptions`,
    # `conversation_memory.load_conversation_memory`).
    existing_assumptions: list[str] = Field(default_factory=list)
    deterministic_intent: str | None = None
    deterministic_intent_confidence: float | None = None
    deterministic_entities: dict[str, Any] = Field(default_factory=dict)
    user_profile_summary: dict[str, Any] = Field(default_factory=dict)
    attachment_metadata: list[dict[str, Any]] = Field(default_factory=list)
    supported_intents: list[str] = Field(default_factory=list)
    supported_workflows: list[str] = Field(default_factory=list)
    locale_hint: str | None = None


class TaskUnderstandingOutput(BaseModel):
    """Structured task-understanding result. Diagnostic in Phase 3."""

    status: TaskUnderstandingStatus

    user_goal: str
    normalized_request: str

    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)

    task_category: TaskCategory
    task_complexity: TaskComplexity

    recommended_autonomy_level: AutonomyLevel
    suggested_next_layer: SuggestedNextLayer

    required_context: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)

    requires_user_confirmation: bool = False
    write_risk: WriteRisk = "none"

    clarifying_questions: list[str] = Field(default_factory=list)

    intent_confidence: float = Field(ge=0.0, le=1.0)
    overall_confidence: float = Field(ge=0.0, le=1.0)

    decision_summary: str
    warnings: list[str] = Field(default_factory=list)

    source: TaskUnderstandingSource = "llm_reasoning_block"
