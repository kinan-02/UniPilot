"""Compact `AgentContextPack` summary for specialist agents (Phase 10).

Deliberately narrow — mirrors `context_compiler.reducers.reduce_agent_context_pack_summary`'s
own whitelist shape, but built directly from a real `AgentContextPack`
object (nothing in the live path today actually produces the pre-shaped
camelCase summary dict that reducer expects). Never includes retrieved wiki
snippet bodies, full `academic_context` blobs, or raw Mongo documents.
"""

from __future__ import annotations

from typing import Any

from app.agent.context_compiler.reducers import sanitize_context_value


def build_agent_context_pack_summary(agent_context_pack: Any | None) -> dict[str, Any]:
    """Compact, sanitized summary of `agent_context_pack`, or `{}` if unavailable.

    Duck-typed (`getattr`-based) so a real `app.agent.schemas.AgentContextPack`
    or a lightweight test double both work; never raises.
    """
    if agent_context_pack is None:
        return {}
    try:
        validation = getattr(agent_context_pack, "validation", None)
        summary = {
            "intent": getattr(agent_context_pack, "intent", None),
            "entities": dict(getattr(agent_context_pack, "entities", None) or {}),
            "assumptions": list(getattr(agent_context_pack, "assumptions", None) or []),
            "missingData": list(getattr(agent_context_pack, "missing_data", None) or []),
            "warnings": list(getattr(agent_context_pack, "warnings", None) or []),
            "validationStatus": getattr(validation, "status", None),
            "validationWarnings": list(getattr(validation, "warnings", None) or []),
            "provenanceCount": len(getattr(agent_context_pack, "provenance", None) or []),
        }
    except Exception:  # noqa: BLE001 — must never crash a caller
        return {}
    return sanitize_context_value(summary)
