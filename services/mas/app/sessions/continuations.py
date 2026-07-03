"""Session continuation metadata for clarify resume and second opinion."""

from __future__ import annotations

from typing import Any


def build_session_lineage(session: dict[str, Any]) -> dict[str, Any] | None:
    """Derive lineage metadata from a persisted agent session document."""
    lineage: dict[str, Any] = {}
    constraints = dict(session.get("constraints") or {})

    source_session_id = constraints.get("secondOpinionOf")
    if source_session_id:
        lineage["kind"] = "second_opinion"
        lineage["sourceSessionId"] = str(source_session_id)
        profile = constraints.get("utilityProfile")
        if profile:
            lineage["utilityProfile"] = str(profile)

    clarifications = list(session.get("clarifications") or [])
    prior_transcript = list(session.get("priorTranscript") or [])
    if clarifications or prior_transcript:
        if "kind" not in lineage:
            lineage["kind"] = "clarification_resume"
        lineage["clarificationCount"] = len(clarifications)
        lineage["priorTranscriptTurns"] = len(prior_transcript)

    if not lineage:
        return None
    return lineage


def merge_lineage_into_decision(
    final_decision: dict[str, Any] | None,
    lineage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if final_decision is None or lineage is None:
        return final_decision
    merged = dict(final_decision)
    merged["sessionLineage"] = lineage
    return merged
