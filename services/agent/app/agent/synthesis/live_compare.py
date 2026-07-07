"""Structural comparison of synthesis candidate vs live response (Phase 22)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentResponse
from app.agent.synthesis.schemas import SynthesisOutput


def compare_synthesis_candidate_to_live_response(
    *,
    candidate_text: str,
    live_response: AgentResponse,
    synthesis_output: SynthesisOutput,
) -> dict[str, Any]:
    """Structural comparison only — never stores candidate or live text."""
    live_text_len = len(live_response.text or "")
    candidate_len = len(candidate_text or "")
    return {
        "candidateExists": bool(candidate_text.strip()),
        "candidateCharCount": candidate_len,
        "liveTextCharCount": live_text_len,
        "candidateLongerThanLive": candidate_len > live_text_len,
        "liveHasBlocks": bool(live_response.blocks),
        "liveProposedActionCount": len(live_response.proposed_actions or []),
        "liveWarningCount": len(live_response.warnings or []),
        "synthesisConflictCount": len(synthesis_output.conflicts),
        "synthesisUncertaintyNoteCount": len(synthesis_output.uncertainty_notes),
    }
