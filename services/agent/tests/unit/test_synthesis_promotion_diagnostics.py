"""Unit tests for synthesis promotion diagnostics (Phase 22)."""

from __future__ import annotations

from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
from app.agent.synthesis.promotion_schemas import SynthesisTextPromotionDecision, SynthesisTextPromotionReason


def test_compact_synthesis_promotion_metadata_built() -> None:
    decision = SynthesisTextPromotionDecision(
        status="blocked",
        mode="shadow_only",
        workflow_name="graduation_progress_workflow",
        synthesis_status="candidate_ready",
        candidate_char_count=120,
        confidence=0.88,
        reasons=[SynthesisTextPromotionReason(code="shadow_only", severity="info")],
        diagnostics={"wouldPromote": True},
    )
    meta = build_synthesis_promotion_metadata(decision)
    assert meta["status"] == "blocked"
    assert meta["preservation"]["blocks"] is True


def test_reasons_capped() -> None:
    reasons = [SynthesisTextPromotionReason(code=f"r{i}") for i in range(20)]
    decision = SynthesisTextPromotionDecision(status="blocked", reasons=reasons)
    meta = build_synthesis_promotion_metadata(decision)
    assert len(meta["reasons"]) <= 12


def test_candidate_text_omitted() -> None:
    decision = SynthesisTextPromotionDecision(
        status="promoted",
        promoted=True,
        diagnostics={"candidate_answer_text": "secret"},
    )
    meta = build_synthesis_promotion_metadata(decision)
    assert "candidate_answer_text" not in meta
    assert "secret" not in str(meta)


def test_live_response_text_omitted() -> None:
    decision = SynthesisTextPromotionDecision(
        status="blocked",
        diagnostics={"liveText": "secret"},
    )
    meta = build_synthesis_promotion_metadata(decision)
    assert "liveText" not in meta


def test_raw_synthesis_output_omitted() -> None:
    decision = SynthesisTextPromotionDecision(status="blocked", diagnostics={"rawEvidence": []})
    meta = build_synthesis_promotion_metadata(decision)
    assert "rawEvidence" not in meta


def test_raw_blocks_omitted() -> None:
    decision = SynthesisTextPromotionDecision(status="blocked", diagnostics={"rawBlocks": []})
    meta = build_synthesis_promotion_metadata(decision)
    assert "rawBlocks" not in meta


def test_no_chain_of_thought_fields() -> None:
    decision = SynthesisTextPromotionDecision(status="skipped")
    meta = build_synthesis_promotion_metadata(decision)
    assert "chain_of_thought" not in meta
