"""Compact synthesis diagnostics (Phase 21)."""

from __future__ import annotations

from typing import Any

from app.agent.synthesis.schemas import SynthesisOutput

_FORBIDDEN_DIAGNOSTIC_KEYS = frozenset(
    {
        "candidate_answer_text",
        "candidateAnswerText",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "rawContext",
        "rawBlocks",
        "proposedActions",
    }
)


def build_synthesis_diagnostics(output: SynthesisOutput) -> dict[str, Any]:
    """Compact counts/status only — never candidate text or raw evidence."""
    high_severity = sum(1 for conflict in output.conflicts if conflict.severity == "error")
    candidate_chars = len(output.candidate_answer_text or "")
    payload = {
        "status": output.status,
        "safeToShow": output.safe_to_show,
        "safeToPromote": False,
        "evidenceItemCount": len(output.evidence_used_ids) + len(output.evidence_excluded_ids),
        "evidenceUsedCount": len(output.evidence_used_ids),
        "evidenceExcludedCount": len(output.evidence_excluded_ids),
        "conflictCount": len(output.conflicts),
        "highSeverityConflictCount": high_severity,
        "uncertaintyNoteCount": len(output.uncertainty_notes),
        "candidateCharCount": candidate_chars,
        "confidence": round(output.confidence, 3),
        "warnings": list(output.warnings[:10]),
        "decisionSummary": output.decision_summary[:200],
    }
    for key in list(payload):
        if key in _FORBIDDEN_DIAGNOSTIC_KEYS:
            payload.pop(key, None)
    return payload


def compare_synthesis_to_live_response(
    *,
    synthesis_output: SynthesisOutput,
    live_response_summary: dict[str, Any],
) -> dict[str, Any]:
    live_preview = str((live_response_summary or {}).get("textPreview") or "")
    candidate = synthesis_output.candidate_answer_text or ""
    return {
        "candidateExists": bool(candidate),
        "candidateLongerThanLive": len(candidate) > len(live_preview),
        "candidateMentionsUncertainty": bool(synthesis_output.uncertainty_notes),
        "liveHasBlocks": bool((live_response_summary or {}).get("blockCount")),
        "synthesisSafeToShow": synthesis_output.safe_to_show,
    }
