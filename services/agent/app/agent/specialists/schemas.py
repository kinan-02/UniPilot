"""Typed models for read-only specialist agents (Phase 10).

Specialist agents are structured, `ReasoningBlock`-powered workers that take
a single planner subtask + a compiled, minimal context pack and produce a
schema-validated structured result — never raw prose, never chain-of-thought,
and (in Phase 10) never a write or an action proposal.

As with every other Phase 1–9 agent model, no field here may carry raw
chain-of-thought or private model reasoning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.agent.specialists.tools.schemas import SpecialistObservationStatus
from app.agent.specialists.tools.tool_loop_schemas import SpecialistToolLoopDiagnostics

SpecialistAgentStatus = Literal[
    "completed",
    "needs_more_context",
    "unsupported",
    "failed",
    "skipped",
]

# Phase 10 implements exactly these three read-only specialists. Write/
# proposal-capable specialists (`transcript_import_agent`,
# `semester_planning_agent`, and any future `action_proposal_agent`/
# `profile_update_agent`) are deliberately out of scope — see
# `capabilities/default_registry.py` and `specialists/registry.py`.
SpecialistAgentKind = Literal[
    "graduation_progress_agent",
    "course_catalog_agent",
    "requirement_explanation_agent",
]


class SpecialistToolObservation(BaseModel):
    """A pre-computed, deterministic observation supplied to a specialist.

    Phase 10 never wired a live tool-execution loop for specialists — this
    list was always empty. Phase 12 adds a deterministic, bounded
    observation-gathering layer (`specialists.tools.observation_builder`)
    that can populate this list from already-available data
    (`AgentContextPack`/`compiled_context`/`dependency_outputs`) — still
    shadow-only, still never a live tool-execution loop driven by the LLM
    itself. `status` mirrors `specialists.tools.schemas.SpecialistObservationStatus`
    so a specialist can tell an `"available"` observation from a `"missing"`
    one (source data not available yet) without ever inventing a value for
    the latter.
    """

    name: str
    status: SpecialistObservationStatus = "available"
    summary: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SpecialistAgentInput(BaseModel):
    """Everything one specialist-agent call needs for one subtask."""

    subtask_id: str
    agent_name: SpecialistAgentKind
    objective: str
    user_message: str
    compiled_context: dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: dict[str, Any] = Field(default_factory=dict)
    deterministic_observations: list[SpecialistToolObservation] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)
    dry_run: bool = True


class SpecialistAgentOutput(BaseModel):
    """Structured result of one specialist-agent call.

    `proposed_actions` is a hard Phase 10 invariant, not a caller-configurable
    field: the validator below forces it to `[]` regardless of what a caller
    (or a misbehaving LLM result) tries to set it to, so no specialist can
    ever actually produce a proposed action in this phase.
    """

    status: SpecialistAgentStatus
    agent_name: SpecialistAgentKind
    subtask_id: str
    result: dict[str, Any] = Field(default_factory=dict)
    decision_summary: str
    key_findings: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    proposed_actions: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 13: set only when the bounded tool-request loop actually ran for
    # this call (i.e. the specialist returned `needs_tool` and the loop is
    # enabled) -- `None` otherwise, so `output_summarizer`/`supervisor_handler`
    # never attach tool-loop keys when the loop never engaged. Diagnostic-only:
    # never read to change the response, routing, or the Phase 9 promotion gate.
    tool_loop_diagnostics: SpecialistToolLoopDiagnostics | None = None

    @field_validator("proposed_actions")
    @classmethod
    def _force_no_proposed_actions(cls, _value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return []
