"""Deterministic trust ranking for synthesis evidence (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.schemas import EvidenceItem, EvidenceTrustLevel, SynthesisConflict

_TRUST_ORDER: dict[EvidenceTrustLevel, int] = {
    "authoritative": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "untrusted": 4,
}


def rank_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return sorted(
        items,
        key=lambda item: (
            _TRUST_ORDER.get(item.trust_level, 99),
            -item.confidence,
            item.id,
        ),
    )


def filter_trusted_for_answer(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    used: list[EvidenceItem] = []
    excluded: list[EvidenceItem] = []
    for item in items:
        if not item.supports_final_answer or item.trust_level in {"untrusted"}:
            excluded.append(item)
            continue
        if item.trust_level == "low" and item.provenance == "assumed":
            excluded.append(item)
            continue
        used.append(item)
    return used, excluded


def monitor_blocks_promotion(monitor_summary: dict[str, Any]) -> bool:
    if not isinstance(monitor_summary, dict):
        return False
    decision = monitor_summary.get("decision") if isinstance(monitor_summary.get("decision"), dict) else {}
    if str(decision.get("action") or "") == "abort_safely":
        return True
    for signal in monitor_summary.get("signals") or []:
        if isinstance(signal, dict) and signal.get("kind") == "unsafe_output":
            return True
    return False


def unresolved_high_severity_conflicts(conflicts: list[SynthesisConflict]) -> bool:
    return any(conflict.severity == "error" and conflict.resolution == "unresolved" for conflict in conflicts)


def only_untrusted_evidence(used: list[EvidenceItem]) -> bool:
    return bool(used) and all(item.trust_level in {"low", "untrusted"} for item in used)
