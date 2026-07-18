"""Shared output envelope for every tool primitive (docs/agent/AGENT_VISION.md §5.1).

Fail-closed by construction: a stub or a real implementation that cannot
determine an answer must return `ok=False` with a populated `error`, never a
placeholder that looks like a success.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.planning.state import CertaintyTag

NOT_IMPLEMENTED = "not_implemented"


class ToolOutputEnvelope(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    certainty: CertaintyTag | None = None
    error: str | None = None
    # Non-fatal caveats about an `ok=True` result (e.g. "found via wiki
    # only, not in the active semester catalog") -- feeds directly into
    # AGENT_VISION.md §7.3's `SubagentResult.warnings` one layer up. Empty
    # by default so every existing call site stays unaffected.
    warnings: list[str] = Field(default_factory=list)
    # Per-field certainty overrides (§4.2). One result can mix provenance:
    # check_eligibility's `eligible` is an official record while its `schedulable`
    # depends on an offering PREDICTION. This maps a data-relative path (e.g.
    # "schedulable", "offeringPattern") -- or a prefix of one -- to THAT field's
    # basis/confidence, so a surfaced fact resolves its basis per field and a
    # prediction can no longer be laundered into a flat official fact. A surfaced
    # value falls back to `certainty` when no path here matches. Empty by default,
    # so every existing tool and call site is unaffected.
    field_certainty: dict[str, CertaintyTag] = Field(default_factory=dict)


def not_implemented_envelope(tool_name: str) -> ToolOutputEnvelope:
    """The stub result every primitive returns until it has a real implementation."""
    return ToolOutputEnvelope(ok=False, data=None, certainty=None, error=f"{NOT_IMPLEMENTED}: {tool_name}")


__all__ = ["NOT_IMPLEMENTED", "ToolOutputEnvelope", "not_implemented_envelope"]
