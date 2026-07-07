"""Deterministic, compact summarizer for a real workflow's `AgentResponse` (Phase 7).

Converts an `AgentResponse` (the same final payload the live orchestrator
would compose) into a compact `output_summary` dict safe to store on the
blackboard/`SubtaskExecutionRecord`/diagnostics — never the full response
text, full structured blocks, raw proposed-action payloads, raw sources, or
anything chain-of-thought-shaped. Purely deterministic: no LLM calls, no I/O.
"""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentResponse

_TEXT_PREVIEW_MAX_LENGTH = 240
_MAX_BLOCK_TYPES_LISTED = 20


def summarize_agent_response(
    response: AgentResponse,
    *,
    workflow_name: str,
    shadow_executed: bool = True,
) -> dict[str, Any]:
    """Compact summary of `response` — see module docstring for what's excluded."""
    text = response.text or ""
    preview = text[:_TEXT_PREVIEW_MAX_LENGTH]
    if len(text) > _TEXT_PREVIEW_MAX_LENGTH:
        preview = preview.rstrip() + "…"

    block_types = [block.type for block in response.blocks][:_MAX_BLOCK_TYPES_LISTED]
    has_proposed_actions = bool(response.proposed_actions)

    return {
        "shadowExecuted": shadow_executed,
        "workflowName": workflow_name,
        "responseType": "AgentResponse",
        "textPreview": preview,
        "blockCount": len(response.blocks),
        "blockTypes": block_types,
        "warningCount": len(response.warnings),
        "sourceCount": len(response.used_sources),
        "proposedActionCount": len(response.proposed_actions),
        "hasProposedActions": has_proposed_actions,
        # `AgentResponse` carries no confidence field today; a mild,
        # deterministic proxy (lower when the response itself reported
        # warnings) is more honest than a hardcoded constant.
        "confidence": 0.8 if response.warnings else 1.0,
    }


def unsafe_output_summary(*, workflow_name: str, reason: str) -> dict[str, Any]:
    """Compact summary for a response that must be discarded (e.g. unexpected proposed actions)."""
    return {
        "shadowExecuted": False,
        "workflowName": workflow_name,
        "responseType": "AgentResponse",
        "reason": reason,
    }
