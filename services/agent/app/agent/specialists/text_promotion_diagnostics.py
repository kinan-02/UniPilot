"""Compact `specialistTextPromotion` metadata shape (Phase 14).

Converts a `SpecialistTextPromotionDecision` into the small, storage-safe
dict attached to `agent_runs.retrievalMetadata.specialistTextPromotion` —
mirrors `supervisor.promotion_diagnostics.build_supervisor_promotion_metadata`
(Phase 9) exactly: never the raw promoted answer text, raw specialist
result, raw observations, raw tool-request arguments, raw compiled context,
or raw workflow response. Purely deterministic: no LLM calls, no I/O.
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.text_promotion_schemas import SpecialistTextPromotionDecision

_MAX_REASONS_LISTED = 20


def build_specialist_text_promotion_metadata(decision: SpecialistTextPromotionDecision) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.specialistTextPromotion` — see module docstring."""
    payload = {
        "status": decision.status,
        "promoted": decision.promoted,
        "mode": decision.mode,
        "workflowName": decision.workflow_name,
        "specialistAgentName": decision.specialist_agent_name,
        "reasons": [
            {"code": reason.code, "severity": reason.severity} for reason in decision.reasons[:_MAX_REASONS_LISTED]
        ],
    }
    runtime_readiness = decision.diagnostics.get("runtimeReadiness")
    if isinstance(runtime_readiness, dict):
        payload["runtimeReadiness"] = {
            key: runtime_readiness.get(key)
            for key in ("gateEnabled", "candidateId", "allowed", "level", "reviewed", "scopeAllowed", "stale", "reasons")
        }
    return payload


__all__ = ["build_specialist_text_promotion_metadata"]
