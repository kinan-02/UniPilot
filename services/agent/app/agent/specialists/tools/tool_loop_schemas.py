"""Typed models for the Bounded Specialist Tool-Request Loop (Phase 13).

A specialist's `ReasoningBlock` pass may return `status="needs_tool"` with a
list of `ReasoningToolRequest`s (Phase 1 foundation, `reasoning/schemas.py`).
Phase 13 lets a specialist's *only* usable "tool" be a request for one more
Phase 12 observation from the existing, fixed
`specialists.tools.registry.SpecialistObservationRegistry` -- there is no
arbitrary tool namespace, no function-call dispatch, and no way to reach a
database, an internal API, or a write/proposal path from here.

As with every other specialist model, no field here may carry raw
chain-of-thought, private model reasoning, raw compiled context, or raw
observation content -- only observation *names*, purposes, and compact
counts ever appear on `SpecialistToolLoopDiagnostics`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SpecialistToolLoopStatus = Literal[
    "completed",
    "completed_with_tools",
    "skipped",
    "failed",
    "budget_exceeded",
]

SpecialistToolRequestStatus = Literal[
    "approved",
    "rejected",
    "unavailable",
    "failed",
]


class SpecialistObservationToolRequest(BaseModel):
    """One specialist-requested observation, coerced from a `ReasoningToolRequest`.

    `observation_name` is expected to be the exact `tool_name` value the
    specialist's `ReasoningBlock` pass returned -- this module never invents
    or guesses one. `arguments` is only ever inspected for forbidden keys
    (`tool_loop_safety.find_forbidden_argument_keys`); it is never persisted
    or forwarded to the observation builder itself, which only accepts
    observation *names*.
    """

    observation_name: str
    purpose: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class SpecialistObservationToolResult(BaseModel):
    """Outcome of validating (and, if approved, executing) one tool request.

    `summary` is intentionally always empty here -- the actual observation
    content lives only in the `SpecialistToolObservation` appended to
    `SpecialistAgentInput.deterministic_observations` for the next reasoning
    pass, never in a diagnostics-facing model like this one.
    """

    observation_name: str
    status: SpecialistToolRequestStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SpecialistToolLoopDiagnostics(BaseModel):
    """Compact, diagnostic-only summary of one specialist's tool-request loop.

    Never carries raw tool-request arguments or raw observation summaries --
    only observation *names* and counts. Safe to fold into
    `SubtaskResult.output_summary` (see `tool_loop_diagnostics.py`), exactly
    like Phase 12's own `_observation_metadata`.
    """

    status: SpecialistToolLoopStatus
    rounds_used: int = 0
    requested_observations: list[str] = Field(default_factory=list)
    approved_observations: list[str] = Field(default_factory=list)
    rejected_observations: list[str] = Field(default_factory=list)
    missing_observations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "SpecialistObservationToolRequest",
    "SpecialistObservationToolResult",
    "SpecialistToolLoopDiagnostics",
    "SpecialistToolLoopStatus",
    "SpecialistToolRequestStatus",
]
