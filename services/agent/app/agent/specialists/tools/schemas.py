"""Typed models for the Specialist Tool Observation Layer (Phase 12).

Deterministic, read-only, bounded observations a specialist agent may
receive alongside `compiled_context`/`dependency_outputs` before its
`ReasoningBlock` call. Nothing here executes a tool, calls an LLM, reads a
database, or performs a write -- see `observation_builder.py` for the
(also side-effect-free) code that actually populates these models from
already-available in-memory data.

As with every other specialist model, no field here may carry raw
chain-of-thought, private model reasoning, raw compiled context, or a
proposed-action payload -- `safety.py` sanitizes every `summary` before it
is attached to a `SpecialistObservation`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SpecialistObservationSource = Literal[
    "agent_context_pack",
    "compiled_context",
    "conversation_memory",
    "retrieval",
    "internal_api",
    "deterministic_summary",
]

SpecialistObservationStatus = Literal[
    "available",
    "missing",
    "skipped",
    "failed",
]


class SpecialistObservation(BaseModel):
    """One compact, sanitized, read-only observation for a specialist agent."""

    name: str
    status: SpecialistObservationStatus = "available"
    source: SpecialistObservationSource
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SpecialistObservationRequest(BaseModel):
    """Everything `observation_builder.build_specialist_observations` needs
    to deterministically build one specialist's observation bundle.

    `compiled_context`/`agent_context_pack_summary`/`dependency_outputs`
    are already-compact/already-sanitized data the caller has on hand --
    this request never carries a raw `AgentContextPack` itself (that is
    passed separately, out-of-schema, exactly like
    `specialists.context.build_agent_context_pack_summary` already does for
    the same reason: it is a live Python object, not JSON-serializable
    request data).
    """

    specialist_agent_name: str
    subtask_id: str
    objective: str
    user_message: str
    compiled_context: dict[str, Any] = Field(default_factory=dict)
    agent_context_pack_summary: dict[str, Any] = Field(default_factory=dict)
    dependency_outputs: dict[str, Any] = Field(default_factory=dict)
    allowed_observations: list[str] = Field(default_factory=list)
    max_observations: int = 8


class SpecialistObservationBundle(BaseModel):
    """Result of one `build_specialist_observations` call.

    `omitted_observations` lists observation names that were requested (or
    otherwise eligible) but not built -- e.g. not allowed for this
    specialist, unknown to the registry, or dropped for exceeding
    `max_observations`. Never includes raw observation content.
    """

    specialist_agent_name: str
    subtask_id: str
    observations: list[SpecialistObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    omitted_observations: list[str] = Field(default_factory=list)
