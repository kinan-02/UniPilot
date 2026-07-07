"""Deterministic fallback synthesis composer (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.conflict_detection import detect_synthesis_conflicts
from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput
from app.agent.synthesis.trust_policy import (
    filter_trusted_for_answer,
    monitor_blocks_promotion,
    only_untrusted_evidence,
    rank_evidence_items,
    unresolved_high_severity_conflicts,
)
from app.config import Settings


def deterministic_synthesis(input: SynthesisInput, settings: Settings) -> SynthesisOutput:
    ranked = rank_evidence_items(input.evidence_items)
    used, excluded = filter_trusted_for_answer(ranked)
    conflicts = detect_synthesis_conflicts(
        input.evidence_items,
        monitor_summary=input.monitor_summary,
        plan_repair_summary=input.plan_repair_summary,
        max_conflicts=max(1, int(settings.agent_synthesis_max_conflicts)),
    )

    uncertainty_notes: list[str] = []
    for item in input.evidence_items:
        if item.provenance == "assumed" or item.trust_level == "low":
            uncertainty_notes.append(f"Assumed or low-trust evidence from {item.source_name}.")

    if monitor_blocks_promotion(input.monitor_summary):
        return SynthesisOutput(
            status="unsafe",
            synthesis_id=input.synthesis_id,
            decision_summary="Monitor flagged unsafe output; synthesis candidate withheld.",
            uncertainty_notes=uncertainty_notes,
            conflicts=conflicts,
            evidence_used_ids=[item.id for item in used],
            evidence_excluded_ids=[item.id for item in excluded],
            safe_to_show=False,
            safe_to_promote=False,
            confidence=0.0,
            warnings=["monitor_unsafe_output"],
        )

    if unresolved_high_severity_conflicts(conflicts):
        return SynthesisOutput(
            status="needs_clarification",
            synthesis_id=input.synthesis_id,
            decision_summary="Unresolved high-severity conflicts prevent a safe candidate.",
            uncertainty_notes=uncertainty_notes,
            conflicts=conflicts,
            evidence_used_ids=[item.id for item in used],
            evidence_excluded_ids=[item.id for item in excluded],
            safe_to_show=False,
            safe_to_promote=False,
            confidence=0.2,
            warnings=["unresolved_conflicts"],
            requested_next_step="ask_clarification",
        )

    if not used or only_untrusted_evidence(used):
        return SynthesisOutput(
            status="insufficient_evidence",
            synthesis_id=input.synthesis_id,
            decision_summary="Insufficient trusted evidence for a synthesis candidate.",
            uncertainty_notes=uncertainty_notes,
            conflicts=conflicts,
            evidence_used_ids=[item.id for item in used],
            evidence_excluded_ids=[item.id for item in excluded],
            safe_to_show=False,
            safe_to_promote=False,
            confidence=0.1,
            warnings=["insufficient_evidence"],
            requested_next_step="retrieve_more_context",
        )

    key_points = [item.claim for item in used[:5]]
    preview = str(input.live_response_summary.get("textPreview") or "").strip()
    candidate_parts = [preview] if preview else []
    candidate_parts.extend(point for point in key_points if point not in candidate_parts)
    candidate_text = "\n".join(part for part in candidate_parts if part).strip()
    max_chars = max(500, int(settings.agent_synthesis_max_candidate_chars))
    candidate_text = candidate_text[:max_chars]

    status = "candidate_ready_with_warnings" if uncertainty_notes or conflicts else "candidate_ready"
    confidence = min(0.95, sum(item.confidence for item in used) / len(used))

    return SynthesisOutput(
        status=status,  # type: ignore[arg-type]
        synthesis_id=input.synthesis_id,
        candidate_answer_text=candidate_text or None,
        decision_summary="Deterministic synthesis composed candidate from trusted evidence.",
        key_points=key_points,
        uncertainty_notes=uncertainty_notes,
        conflicts=conflicts,
        evidence_used_ids=[item.id for item in used],
        evidence_excluded_ids=[item.id for item in excluded],
        safe_to_show=bool(candidate_text),
        safe_to_promote=False,
        confidence=confidence,
        warnings=[],
    )
