"""Adaptive planning schemas (docs/agent/AGENT_VISION.md §3, §3.1, §10).

Deliberately not a port of `services/agent/app/agent/planner/schemas.py` --
that shape is fixed-upfront (a full `subtasks` list decided in one pass) and
tied to the old fixed-workflow/capability-registry system. This module
supports the vision's adaptive rhythm instead: the Planner is invoked
repeatedly, each time producing only the next runnable chunk of steps, never
a full plan with placeholders for steps it doesn't yet have grounds to
decide.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RoleName = Literal[
    "retrieval",
    "interpretation",
    "calculation_validation",
    "simulation_planning",
    "composition",
]

PlanStatus = Literal["in_progress", "complete", "blocked_needs_clarification"]

RiskLevel = Literal["low", "medium", "high"]


class PlanStep(BaseModel):
    """One unit of work the Orchestrator will dispatch to a subagent."""

    step_id: str
    title: str
    objective: str
    role: RoleName
    depends_on: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    # What the Monitor checks this step's result against (see orchestrator.monitor).
    assumptions_to_verify: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "medium"


class StateEntrySummary(BaseModel):
    """Compact index of one `StateEntry` -- what the Planner sees of prior
    results, never the full payload (keeps the Planner's own context bounded)."""

    entry_id: str
    step_id: str
    role: RoleName
    summary: str
    certainty_band: Literal["high", "medium", "low"]


class PlannerInvocationInput(BaseModel):
    """Everything one Planner invocation needs.

    `sub_asks`/`constraints`/`open_questions`/`implies_action_request` come
    from Request Understanding's own structured output (never lossily
    flattened into `user_goal` alone) -- additive fields, default
    empty/`False` for any caller that doesn't supply them.
    """

    user_goal: str
    original_user_message: str
    sub_asks: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    implies_action_request: bool = False
    state_index: list[StateEntrySummary] = Field(default_factory=list)
    monitor_flags: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class PlannerInvocationOutput(BaseModel):
    """What one Planner invocation returns -- the next chunk only.

    `plan_status` is explicit, never inferred from `next_steps` being empty
    (empty could mean "done" or "nothing to add this round due to a bug" --
    ambiguity this field removes entirely).
    """

    plan_status: PlanStatus
    next_steps: list[PlanStep] = Field(default_factory=list)
    plan_summary: str
    # Non-binding breadcrumbs for the *next* Planner call's own context --
    # never structure the Orchestrator could accidentally dispatch.
    anticipated_followup: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


__all__ = [
    "RoleName",
    "PlanStatus",
    "RiskLevel",
    "PlanStep",
    "StateEntrySummary",
    "PlannerInvocationInput",
    "PlannerInvocationOutput",
]
