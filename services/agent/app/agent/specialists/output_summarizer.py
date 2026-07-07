"""Deterministic, compact summarizer for a `SpecialistAgentOutput` (Phase 10).

Mirrors `supervisor.output_summarizer.summarize_agent_response` — converts a
full `SpecialistAgentOutput` into a compact dict safe to store as a
`SubtaskResult.output_summary` / supervisor diagnostics. Never the full
`result` payload, raw compiled context, raw prompts, or chain-of-thought.
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.schemas import SpecialistAgentOutput

_TEXT_PREVIEW_MAX_LENGTH = 240
_MAX_RESULT_KEYS_LISTED = 20


def summarize_specialist_output(output: SpecialistAgentOutput) -> dict[str, Any]:
    """Compact summary of `output` — see module docstring for what's excluded."""
    decision_summary = output.decision_summary or ""
    preview = decision_summary[:_TEXT_PREVIEW_MAX_LENGTH]
    if len(decision_summary) > _TEXT_PREVIEW_MAX_LENGTH:
        preview = preview.rstrip() + "…"

    return {
        "agentName": output.agent_name,
        "status": output.status,
        "confidence": output.confidence,
        "keyFindingCount": len(output.key_findings),
        "warningCount": len(output.warnings),
        "sourceCount": len(output.sources),
        "missingContextCount": len(output.missing_context),
        "hasProposedActions": bool(output.proposed_actions),
        "resultKeys": sorted(output.result.keys())[:_MAX_RESULT_KEYS_LISTED],
        "decisionSummaryPreview": preview,
    }
