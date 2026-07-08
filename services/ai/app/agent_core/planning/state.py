"""Shared plan-execution state (docs/agent/AGENT_VISION.md §3.2, §8).

Every result a subagent produces is appended here with an explicit certainty
tag that must survive being read by later steps and by Synthesis, never
collapsing into "just a fact" along the way.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent_core.planning.schemas import RoleName

CertaintyBasis = Literal[
    "official_record",
    "wiki_derived",
    "predicted_pattern",
    "llm_interpretation",
    "hypothetical_simulation",
]

StepStatus = Literal["succeeded", "partial", "failed"]


class SourceRef(BaseModel):
    page: str
    section: str | None = None
    reasoning_path: str | None = None


class CertaintyTag(BaseModel):
    basis: CertaintyBasis
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: SourceRef | None = None


class ToolInvocationRecord(BaseModel):
    """One entry in a subagent's tool-call audit trail."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    output_ok: bool
    output_certainty: CertaintyTag | None = None


class StateEntry(BaseModel):
    entry_id: str
    step_id: str
    role: RoleName
    status: StepStatus
    output_schema_name: str
    data: dict[str, Any] = Field(default_factory=dict)
    certainty: CertaintyTag
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)
    produced_at: datetime


class PlanExecutionState(BaseModel):
    """Append-only. A retried step (after a Monitor-triggered replan) appends
    a second entry rather than overwriting history -- this keeps the record
    of *why* a replan happened intact, auditable after the fact."""

    plan_id: str
    entries: list[StateEntry] = Field(default_factory=list)

    def append(self, entry: StateEntry) -> None:
        self.entries.append(entry)

    def by_step(self, step_id: str) -> StateEntry | None:
        for entry in reversed(self.entries):
            if entry.step_id == step_id:
                return entry
        return None

    def slice(self, step_ids: list[str]) -> list[StateEntry]:
        wanted = set(step_ids)
        return [entry for entry in self.entries if entry.step_id in wanted]


__all__ = [
    "CertaintyBasis",
    "StepStatus",
    "SourceRef",
    "CertaintyTag",
    "ToolInvocationRecord",
    "StateEntry",
    "PlanExecutionState",
]
