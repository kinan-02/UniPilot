"""Compact runtime readiness diagnostics (Phase 25)."""

from __future__ import annotations

from typing import Any

from app.agent.readiness.schemas import RuntimeReadinessGateDecision
from app.config import Settings


def build_runtime_readiness_diagnostic(
    decision: RuntimeReadinessGateDecision,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Compact runtimeReadiness payload — no manifest, no eval report, no raw text."""
    return {
        "gateEnabled": settings.is_agent_runtime_readiness_gate_enabled(),
        "candidateId": decision.candidate_id,
        "allowed": decision.allowed,
        "level": decision.level,
        "reviewed": decision.reviewed,
        "scopeAllowed": decision.scope_allowed,
        "stale": decision.stale,
        "reasons": list(decision.reasons[:8]),
    }


def build_turn_runtime_readiness_metadata(
    *,
    settings: Settings,
    promotion_diagnostics: list[dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Aggregate compact top-level retrievalMetadata.runtimeReadiness."""
    if not settings.is_agent_runtime_readiness_gate_enabled():
        return None

    decisions: list[dict[str, Any]] = []
    for item in promotion_diagnostics:
        if not isinstance(item, dict):
            continue
        nested = item.get("runtimeReadiness")
        if not isinstance(nested, dict):
            continue
        decisions.append(
            {
                "candidateId": nested.get("candidateId"),
                "allowed": nested.get("allowed"),
                "reasonCount": len(nested.get("reasons") or []),
            }
        )

    return {
        "gateEnabled": True,
        "decisions": decisions,
    }
