"""Compact synthesisPromotion metadata (Phase 22)."""

from __future__ import annotations

from typing import Any

from app.agent.synthesis.promotion_schemas import SynthesisTextPromotionDecision

_MAX_REASONS = 12
_FORBIDDEN_KEYS = frozenset(
    {
        "candidate_answer_text",
        "candidateAnswerText",
        "liveText",
        "liveResponseText",
        "chain_of_thought",
        "hidden_reasoning",
        "rawContext",
        "rawBlocks",
        "rawEvidence",
    }
)


def build_synthesis_promotion_metadata(decision: SynthesisTextPromotionDecision) -> dict[str, Any]:
    payload = {
        "status": decision.status,
        "promoted": decision.promoted,
        "mode": decision.mode,
        "workflowName": decision.workflow_name,
        "synthesisStatus": decision.synthesis_status,
        "candidateCharCount": decision.candidate_char_count,
        "confidence": round(decision.confidence, 3),
        "reasons": [
            {"code": reason.code, "severity": reason.severity} for reason in decision.reasons[:_MAX_REASONS]
        ],
        "preservation": {
            "blocks": decision.live_blocks_preserved,
            "warnings": decision.live_warnings_preserved,
            "sources": decision.live_sources_preserved,
            "actions": decision.live_actions_preserved,
        },
        **{k: v for k, v in decision.diagnostics.items() if k not in _FORBIDDEN_KEYS},
    }
    runtime_readiness = decision.diagnostics.get("runtimeReadiness")
    if isinstance(runtime_readiness, dict):
        payload["runtimeReadiness"] = {
            key: runtime_readiness.get(key)
            for key in ("gateEnabled", "candidateId", "allowed", "level", "reviewed", "scopeAllowed", "stale", "reasons")
        }
    for key in list(payload):
        if key in _FORBIDDEN_KEYS:
            payload.pop(key, None)
    return payload
