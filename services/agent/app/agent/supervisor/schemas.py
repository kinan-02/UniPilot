"""Typed models for the Supervisor Orchestrator Runtime (Phase 6).

The Supervisor Runtime consumes a normalized `PlannerOutput` (Phase 5) and
executes its subtask graph *mechanics* — dependency ordering, context
compilation, handler dispatch, blackboard updates, retries/budgets — never
real workflows, internal APIs, or writes. Shadow/dry-run only in Phase 6.
As with `PlannerOutput`/`TaskUnderstandingOutput`, no field here may carry
raw chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupervisorRunStatus = Literal[
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
    "budget_exceeded",
]

SubtaskExecutionStatus = Literal[
    "pending",
    "blocked",
    "ready",
    "compiling_context",
    "running",
    "validating",
    "completed",
    "failed",
    "skipped",
    "retrying",
]

SubtaskHandlerKind = Literal[
    "dry_run",
    "context_preview",
    "workflow_adapter",
    "specialist_agent",
    "validator",
    "composer",
]


class ExecutionBudget(BaseModel):
    """Caps enforced by `BudgetTracker` for one supervisor run."""

    max_subtasks: int = 20
    max_retries_per_subtask: int = 1
    max_total_retries: int = 5
    max_runtime_ms: int = 30000
    max_context_previews: int = 20


class SubtaskExecutionRecord(BaseModel):
    """Diagnostic execution record for one subtask (part of `SupervisorRunOutput`)."""

    subtask_id: str
    capability_name: str
    status: SubtaskExecutionStatus
    attempts: int = 0
    depends_on: list[str] = Field(default_factory=list)
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    context_preview: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class SubtaskResult(BaseModel):
    """What a `SubtaskHandler.run(...)` call returns for one subtask attempt."""

    subtask_id: str
    capability_name: str
    status: Literal["completed", "failed", "skipped"]
    output_summary: dict[str, Any] = Field(default_factory=dict)
    produced_context: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SupervisorRunInput(BaseModel):
    """Everything one `run_supervisor_shadow` call needs.

    `planner_output` is the full `PlannerOutput.model_dump()` (not the
    compact `plannerDiagnostics` summary) — the supervisor needs the full
    subtask graph, not a diagnostic rollup of it.
    """

    run_id: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    user_message: str
    planner_output: dict[str, Any]
    task_understanding: dict[str, Any] | None = None
    deterministic_intent: str | None = None
    deterministic_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_assumptions: list[str] = Field(default_factory=list)
    profile_summary: dict[str, Any] = Field(default_factory=dict)
    previous_results: dict[str, Any] = Field(default_factory=dict)
    # Diagnostic breadcrumb only -- no handler in `supervisor.runtime` reads
    # this field. Built-in handlers are unconditionally dry-run stand-ins;
    # whether the real `ReadOnlyWorkflowAdapterHandler` executes is governed
    # solely by `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` +
    # `safety.can_shadow_execute_capability`. Setting this to `False` does
    # not enable real execution -- `run_supervisor_shadow` emits
    # `supervisor_dry_run_flag_has_no_effect_on_shadow_execution` if it is.
    dry_run: bool = True
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)


class SupervisorRuntimeContext(BaseModel):
    """Optional, safe runtime objects a real (Phase 7) handler may need.

    `database`/`agent_context_pack` are intentionally typed `Any` — they
    hold a live Motor database handle and an `AgentContextPack`
    respectively, neither of which needs (or should have) its own
    validation here; this model exists to bundle them safely, not to
    re-validate them.

    `allow_side_effects` and `shadow_execution` are hard Phase 7 invariants,
    not caller-configurable knobs: the validators below force them to
    `False`/`True` respectively regardless of what a caller passes in, so a
    future accidental `allow_side_effects=True` call site can never
    actually enable a write from within the supervisor runtime.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    database: Any | None = None
    agent_context_pack: Any | None = None
    user_message: str = ""
    user_id: str | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    allow_side_effects: bool = False
    shadow_execution: bool = True

    @field_validator("allow_side_effects")
    @classmethod
    def _force_no_side_effects(cls, _value: bool) -> bool:
        return False

    @field_validator("shadow_execution")
    @classmethod
    def _force_shadow_execution(cls, _value: bool) -> bool:
        return True


class SupervisorRunOutput(BaseModel):
    """Compact result of one supervisor shadow run. Diagnostic only in Phase 6."""

    status: SupervisorRunStatus
    plan_id: str
    execution_mode: str
    subtask_records: list[SubtaskExecutionRecord] = Field(default_factory=list)
    completed_subtasks: list[str] = Field(default_factory=list)
    failed_subtasks: list[str] = Field(default_factory=list)
    skipped_subtasks: list[str] = Field(default_factory=list)
    blackboard_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
