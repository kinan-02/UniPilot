"""Compact, diagnostic-only summary of a `SpecialistToolLoopDiagnostics` (Phase 13).

Mirrors `specialists.supervisor_handler._observation_metadata` (Phase 12) --
converts a full `SpecialistToolLoopDiagnostics` into the small, fixed-shape
dict safe to fold into `SubtaskResult.output_summary`. Only observation
*names* and counts ever appear here -- never raw tool-request arguments,
never raw observation summaries.
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.tools.tool_loop_schemas import SpecialistToolLoopDiagnostics


def build_tool_loop_diagnostics_summary(diagnostics: SpecialistToolLoopDiagnostics) -> dict[str, Any]:
    """Compact summary of `diagnostics` -- see module docstring for what's excluded."""
    return {
        "toolLoopStatus": diagnostics.status,
        "toolLoopRoundsUsed": diagnostics.rounds_used,
        "requestedObservationCount": len(diagnostics.requested_observations),
        "approvedObservationCount": len(diagnostics.approved_observations),
        "rejectedObservationCount": len(diagnostics.rejected_observations),
        "requestedObservationNames": list(diagnostics.requested_observations),
        "rejectedObservationNames": list(diagnostics.rejected_observations),
    }


__all__ = ["build_tool_loop_diagnostics_summary"]
