"""Compact `supervisorPromotion` metadata shape (Phase 9).

Converts a `PromotionDecision` into the small, storage-safe dict attached to
`agent_runs.retrievalMetadata.supervisorPromotion` — never the raw candidate
response, raw live response, raw blocks/text, or raw context. Purely
deterministic: no LLM calls, no I/O.
"""

from __future__ import annotations

from typing import Any

from app.agent.supervisor.promotion_schemas import PromotionDecision

_MAX_REASONS_LISTED = 20


def build_supervisor_promotion_metadata(decision: PromotionDecision) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.supervisorPromotion` — see module docstring."""
    payload = {
        "status": decision.status,
        "promoted": decision.promoted,
        "workflowName": decision.workflow_name,
        "mode": decision.mode,
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
