"""Compose user-facing agent responses from workflow output (spec §24.8)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock


def compose_response(
    *,
    conversation_id: str,
    message_id: str,
    run_id: str,
    text: str,
    blocks: list[StructuredBlock] | None = None,
    warnings: list[str] | None = None,
    suggested_prompts: list[str] | None = None,
    assumptions: list[str] | None = None,
    used_sources: list[str] | None = None,
    proposed_actions: list[ProposedAction] | None = None,
) -> AgentResponse:
    actions: list[ProposedAction] = []
    for item in proposed_actions or []:
        if isinstance(item, ProposedAction):
            actions.append(item)
        elif isinstance(item, dict):
            actions.append(ProposedAction(**item))

    return AgentResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        run_id=run_id,
        text=text,
        blocks=list(blocks or []),
        warnings=list(warnings or []),
        suggested_prompts=list(suggested_prompts or []),
        proposed_actions=actions,
        assumptions=list(assumptions or []),
        used_sources=list(used_sources or []),
    )


def blocks_from_dicts(items: list[dict[str, Any]]) -> list[StructuredBlock]:
    return [
        StructuredBlock(type=str(item.get("type") or "WarningBlock"), data=dict(item.get("data") or {}))
        for item in items
    ]
