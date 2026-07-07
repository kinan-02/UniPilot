"""Typed models for the Planner Agent (Phase 5).

`PlannerAgent` converts a validated `TaskUnderstandingOutput` into a
capability-aware execution plan (subtasks, dependencies, required context,
success criteria) via the shared `ReasoningBlock` runtime. Diagnostic only
in Phase 5 — nothing in the live orchestrator executes this plan or uses it
to select a workflow. As with `TaskUnderstandingOutput`, no field here may
carry raw chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PlannerStatus = Literal["completed", "needs_more_context", "unsupported", "failed"]

PlannerExecutionMode = Literal[
    "deterministic_workflow",
    "single_capability",
    "multi_capability_graph",
    "clarification",
    "unsupported",
]

SubtaskKind = Literal[
    "understand",
    "retrieve_context",
    "analyze",
    "simulate",
    "validate",
    "compose",
    "propose_action",
    "clarify",
]

PlannerRiskLevel = Literal["low", "medium", "high"]
PlannerWriteRisk = Literal["none", "possible", "explicit"]

# 0 — deterministic direct answer only
# 1 — LLM explanation over deterministic result
# 2 — task understanding + deterministic workflow
# 3 — planner needed
# 4 — multi-agent/specialist execution likely needed
# 5 — write/action proposal likely required
#
# Mirrors `app.agent.task_understanding.schemas.AutonomyLevel` — kept as a
# separate Literal here (rather than imported) so the planner package has no
# import-time dependency on `task_understanding`; the two must still be kept
# in sync by convention if the scale ever changes.
PlannerAutonomyLevel = Literal[0, 1, 2, 3, 4, 5]

PlannerSource = Literal["llm_reasoning_block", "deterministic_fallback", "hybrid"]

DynamicAgentSpecStatus = Literal[
    "not_requested",
    "generated",
    "validated",
    "rejected",
    "skipped",
]


class PlannerInput(BaseModel):
    """Minimal, task-specific context for one `build_execution_plan` call.

    Deliberately excludes large context (full catalog, transcript rows,
    degree requirements, wiki snippets, raw Mongo documents) — the planner
    plans the task, it does not solve it. `conversation_assumptions` is
    `list[str]` (not `dict`) to match how assumptions are represented
    everywhere else in the project (`AgentContextPack.assumptions`,
    `conversation_memory.load_conversation_memory`,
    `TaskUnderstandingInput.existing_assumptions`).
    """

    user_message: str
    task_understanding: dict[str, Any] = Field(default_factory=dict)
    deterministic_intent: str | None = None
    deterministic_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_assumptions: list[str] = Field(default_factory=list)
    capability_registry_summary: list[dict[str, Any]] = Field(default_factory=list)
    legacy_workflow_plan: dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list)
    profile_summary: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class PlannerSubtask(BaseModel):
    """One node in the planner's proposed execution graph. Never executed in Phase 5."""

    id: str
    title: str
    kind: SubtaskKind
    capability_name: str
    objective: str
    depends_on: list[str] = Field(default_factory=list)
    required_context_sections: list[str] = Field(default_factory=list)
    expected_output_schema_name: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    can_run_in_parallel_group: str | None = None
    requires_user_confirmation: bool = False
    risk_level: PlannerRiskLevel = "medium"
    dynamic_agent_spec: dict[str, Any] | None = None
    dynamic_agent_spec_status: DynamicAgentSpecStatus | None = None


class PlannerOutput(BaseModel):
    """Structured execution plan / task graph. Diagnostic only in Phase 5."""

    status: PlannerStatus
    plan_id: str
    user_goal: str
    execution_mode: PlannerExecutionMode
    recommended_autonomy_level: PlannerAutonomyLevel
    primary_intent: str

    subtasks: list[PlannerSubtask] = Field(default_factory=list)

    required_context: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    requires_user_confirmation: bool = False
    write_risk: PlannerWriteRisk = "none"

    clarification_questions: list[str] = Field(default_factory=list)
    validation_strategy: list[str] = Field(default_factory=list)
    fallback_workflow_name: str | None = None

    decision_summary: str
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    source: PlannerSource = "llm_reasoning_block"
    dynamic_spec_diagnostics: dict[str, Any] | None = None
