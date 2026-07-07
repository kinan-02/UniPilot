"""Unit tests for synthesis trust policy (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.schemas import EvidenceItem, SynthesisConflict
from app.agent.synthesis.trust_policy import (
    filter_trusted_for_answer,
    monitor_blocks_promotion,
    only_untrusted_evidence,
    rank_evidence_items,
    unresolved_high_severity_conflicts,
)


def _item(source_type: str, trust: str, provenance: str = "deterministic") -> EvidenceItem:
    return EvidenceItem(
        id=f"{source_type}-{trust}",
        source_type=source_type,  # type: ignore[arg-type]
        source_name=source_type,
        claim="claim",
        trust_level=trust,  # type: ignore[arg-type]
        provenance=provenance,  # type: ignore[arg-type]
    )


def test_deterministic_beats_specialist_evidence() -> None:
    ranked = rank_evidence_items([_item("specialist_agent", "medium"), _item("deterministic_workflow", "authoritative")])
    assert ranked[0].source_type == "deterministic_workflow"


def test_deterministic_beats_dynamic_agent_evidence() -> None:
    ranked = rank_evidence_items([_item("dynamic_agent", "medium"), _item("deterministic_workflow", "authoritative")])
    assert ranked[0].source_type == "deterministic_workflow"


def test_confirmed_clarification_beats_assumed_preference() -> None:
    ranked = rank_evidence_items(
        [
            _item("assumed_user_preference", "low", "assumed"),
            _item("confirmed_user_clarification", "high", "confirmed"),
        ]
    )
    assert ranked[0].source_type == "confirmed_user_clarification"


def test_unsafe_monitor_signal_blocks_promotion() -> None:
    assert monitor_blocks_promotion({"decision": {"action": "abort_safely"}})


def test_unresolved_conflict_blocks_promotion() -> None:
    assert unresolved_high_severity_conflicts(
        [SynthesisConflict(id="c1", severity="error", summary="bad", resolution="unresolved")]
    )


def test_only_untrusted_evidence_blocks_candidate_readiness() -> None:
    used, _ = filter_trusted_for_answer([_item("unknown", "low", "assumed")])
    assert only_untrusted_evidence(used) or not used
