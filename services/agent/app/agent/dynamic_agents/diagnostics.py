"""Compact dynamic-agent diagnostics (Phase 15).

Builds sanitized metadata for `agent_runs.retrievalMetadata.dynamicAgents`.
Never stores raw prompts, context, observations, blocks, or proposed actions.
"""

from __future__ import annotations

from typing import Any

from app.agent.dynamic_agents.schemas import DynamicAgentRunOutput

_MAX_WARNINGS_LISTED = 8


def build_dynamic_agent_run_summary(
    output: DynamicAgentRunOutput,
    *,
    reasoning_pattern: str,
    block_count: int,
) -> dict[str, Any]:
    return {
        "specId": output.spec_id,
        "agentName": output.agent_name,
        "reasoningPattern": reasoning_pattern,
        "blockCount": block_count,
        "status": output.status,
        "confidence": output.confidence,
        "warningCount": len(output.warnings),
        "missingContextCount": len(output.missing_context),
    }


def build_dynamic_agents_diagnostics(
    *,
    agent_summaries: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any] | None:
    if not agent_summaries:
        return None

    capped_warnings = list((warnings or [])[:_MAX_WARNINGS_LISTED])
    if any(summary.get("status") == "failed" for summary in agent_summaries):
        status = "failed"
    elif any(summary.get("status") == "needs_more_context" for summary in agent_summaries):
        status = "needs_more_context"
    elif all(summary.get("status") == "skipped" for summary in agent_summaries):
        status = "skipped"
    else:
        status = "completed"

    return {
        "status": status,
        "agentCount": len(agent_summaries),
        "agents": agent_summaries,
        "warnings": capped_warnings,
    }


def build_dynamic_agents_metadata_from_subtask_summaries(
    subtask_summaries: list[dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Scan compact subtask summaries for dynamic-agent shapes."""
    agent_summaries: list[dict[str, Any]] = []
    for summary in subtask_summaries:
        if not isinstance(summary, dict):
            continue
        if "specId" not in summary or "reasoningPattern" not in summary:
            continue
        agent_summaries.append(
            {
                "specId": summary.get("specId"),
                "agentName": summary.get("agentName"),
                "reasoningPattern": summary.get("reasoningPattern"),
                "blockCount": summary.get("blockCount", 0),
                "status": summary.get("status"),
                "confidence": summary.get("confidence", 0.0),
                "warningCount": summary.get("warningCount", 0),
                "missingContextCount": summary.get("missingContextCount", 0),
            }
        )
    return build_dynamic_agents_diagnostics(agent_summaries=agent_summaries)
