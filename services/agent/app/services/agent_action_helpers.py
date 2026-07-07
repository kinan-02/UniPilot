"""Tiny pure helper shared by workflows that create action proposals.

Duplicated intentionally from `api`'s `agent_action_service.py` (a single
~12-line pure dict transform) rather than calling back into `api` for it —
`api`'s confirm/reject execution logic (the part that actually performs the
write) stays exclusively in `api` and is untouched by this migration.
"""

from __future__ import annotations

from typing import Any


def proposal_to_agent_action(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": proposal.get("id"),
        "action_type": proposal.get("type"),
        "label": proposal.get("title") or "Confirm action",
        "title": proposal.get("title") or "Confirm action",
        "description": proposal.get("description"),
        "preview": proposal.get("preview"),
        "requires_confirmation": True,
        "payload": proposal.get("payload") or {},
        "status": proposal.get("status") or "pending",
    }
