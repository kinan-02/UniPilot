"""Certainty tagging and tool-call audit primitives.

Every result a tool produces carries an explicit certainty tag that must
survive being read by later steps, never collapsing into "just a fact" along
the way -- the grounding floor the V2 loop is built on (see
docs/agent/AGENT_ARCHITECTURE_V2.md §3.1).

These four types were extracted from the retired `planning/state.py` during
the V1 teardown: they are the only part of that module the live loop and the
~25 tool primitives/composites ever used, while `PlanExecutionState` /
`StateEntry` belonged to the V1 orchestrator's shared plan state and died with
it. Keeping them here means the tool layer no longer depends on planning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CertaintyBasis = Literal[
    "official_record",
    "wiki_derived",
    "predicted_pattern",
    "llm_interpretation",
    "hypothetical_simulation",
]


class SourceRef(BaseModel):
    page: str
    section: str | None = None
    reasoning_path: str | None = None


class CertaintyTag(BaseModel):
    basis: CertaintyBasis
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: SourceRef | None = None


class ToolInvocationRecord(BaseModel):
    """One entry in a tool-call audit trail."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    output_ok: bool
    output_certainty: CertaintyTag | None = None
    # True when this call was served from the turn-scoped `ToolCallCache`
    # instead of actually invoking the tool -- lets logs/audits distinguish
    # a real call from a reused one (found necessary while investigating why
    # one call's arguments recurred dozens of times across a single turn).
    from_cache: bool = False


__all__ = [
    "CertaintyBasis",
    "SourceRef",
    "CertaintyTag",
    "ToolInvocationRecord",
]
