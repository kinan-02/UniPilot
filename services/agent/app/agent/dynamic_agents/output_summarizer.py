"""Compact summarizer for `DynamicAgentRunOutput` (Phase 15).

Mirrors `specialists.output_summarizer.summarize_specialist_output` — safe
for `SubtaskResult.output_summary` and supervisor diagnostics. Never stores
raw context, prompts, observations, or chain-of-thought.
"""

from __future__ import annotations

from typing import Any

from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentRunOutput

_TEXT_PREVIEW_MAX_LENGTH = 240
_MAX_RESULT_KEYS_LISTED = 20


def summarize_dynamic_agent_output(
    output: DynamicAgentRunOutput,
    *,
    spec: AgentSpec | None = None,
    block_count: int = 0,
) -> dict[str, Any]:
    decision_summary = output.decision_summary or ""
    preview = decision_summary[:_TEXT_PREVIEW_MAX_LENGTH]
    if len(decision_summary) > _TEXT_PREVIEW_MAX_LENGTH:
        preview = preview.rstrip() + "…"

    summary: dict[str, Any] = {
        "specId": output.spec_id,
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
        "blockCount": block_count,
    }
    if spec is not None:
        summary["reasoningPattern"] = spec.reasoning_pattern
    return summary
