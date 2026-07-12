"""Shared plan-execution state (docs/agent/AGENT_VISION.md §3.2, §8).

Every result a subagent produces is appended here with an explicit certainty
tag that must survive being read by later steps and by Synthesis, never
collapsing into "just a fact" along the way.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent_core.planning.schemas import PlanGraph, RoleName

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
    # True when this call was served from the turn-scoped `ToolCallCache`
    # instead of actually invoking the tool -- lets logs/audits distinguish
    # a real call from a reused one (found necessary while investigating why
    # one call's arguments recurred dozens of times across a single turn).
    from_cache: bool = False


class NestedStepTrace(BaseModel):
    """One entry in a task handler's private sub-plan (docs/agent/AGENT_VISION.md
    §7, task-handler follow-up) -- auxiliary/observability record only, never
    consumed by downstream dependents. Preserved on the parent StateEntry so
    debugging and eval logs can see what actually happened inside a
    task-handler-resolved step, without that internal plumbing ever leaking
    into `StateEntry.data`."""

    entry_id: str
    step_id: str
    role: RoleName
    status: StepStatus
    certainty: CertaintyTag
    warnings: list[str] = Field(default_factory=list)


class NestedExecutionTrace(BaseModel):
    """What a task handler's recursive/nested path leaves behind on the final
    StateEntry it hands back to the shared plan state."""

    private_plan_id: str
    rounds_used: int
    rounds_exhausted: bool = False
    entries: list[NestedStepTrace] = Field(default_factory=list)
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)


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
    # Present only when this entry was produced by a task handler's nested
    # sub-plan rather than one direct specialist dispatch -- auxiliary
    # metadata, never read by any downstream step's own dependency slicing.
    nested_trace: NestedExecutionTrace | None = None


class PlanExecutionState(BaseModel):
    """Append-only. A retried step (after a Monitor-triggered replan) appends
    a second entry rather than overwriting history -- this keeps the record
    of *why* a replan happened intact, auditable after the fact."""

    plan_id: str
    entries: list[StateEntry] = Field(default_factory=list)
    # Whole-plan graph accumulated across every Planner invocation so far
    # (docs/agent/PLANNER_OUTPUT_DESIGN.md §5) -- the single persistent
    # accumulator each invocation's own delta `PlanGraph` merges into.
    plan_graph: PlanGraph = Field(default_factory=PlanGraph)

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

    def merge_plan_graph(self, delta: PlanGraph) -> None:
        """Fold one Planner invocation's own delta graph into the
        accumulated whole-plan view. `forward` keys are always new (a step
        id is only ever produced once), so a plain update is safe.
        `dependents` entries can grow on *either* side -- a new step in this
        delta may point back at an already-accumulated step, or an already-
        accumulated key may already have entries from an earlier merge --
        so existing lists are extended, not overwritten. `execution_layers`
        is appended, not recomputed: a later invocation's steps can only
        exist because an earlier invocation's relevant results already came
        back, so cross-invocation layers are strictly sequential."""
        self.plan_graph.forward.update(delta.forward)
        for step_id, new_dependents in delta.dependents.items():
            existing = self.plan_graph.dependents.setdefault(step_id, [])
            existing.extend(dependent for dependent in new_dependents if dependent not in existing)
        self.plan_graph.execution_layers.extend(delta.execution_layers)


__all__ = [
    "CertaintyBasis",
    "StepStatus",
    "SourceRef",
    "CertaintyTag",
    "ToolInvocationRecord",
    "NestedStepTrace",
    "NestedExecutionTrace",
    "StateEntry",
    "PlanExecutionState",
]
