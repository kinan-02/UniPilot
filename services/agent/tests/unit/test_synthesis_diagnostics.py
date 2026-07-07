"""Unit tests for synthesis diagnostics (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.diagnostics import build_synthesis_diagnostics, compare_synthesis_to_live_response
from app.agent.synthesis.schemas import SynthesisOutput


def test_compact_synthesis_diagnostics_built() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="composed",
        candidate_answer_text="secret candidate",
        evidence_used_ids=["a"],
        evidence_excluded_ids=["b"],
        safe_to_show=True,
    )
    diag = build_synthesis_diagnostics(out)
    assert diag["status"] == "candidate_ready"


def test_evidence_counts_included() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        evidence_used_ids=["a", "b"],
        evidence_excluded_ids=["c"],
    )
    diag = build_synthesis_diagnostics(out)
    assert diag["evidenceUsedCount"] == 2
    assert diag["evidenceExcludedCount"] == 1


def test_conflict_counts_included() -> None:
    from app.agent.synthesis.schemas import SynthesisConflict

    out = SynthesisOutput(
        status="candidate_ready_with_warnings",
        synthesis_id="s",
        decision_summary="x",
        conflicts=[SynthesisConflict(id="c1", severity="warning", summary="warn")],
    )
    diag = build_synthesis_diagnostics(out)
    assert diag["conflictCount"] == 1


def test_candidate_char_count_included() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="12345",
    )
    diag = build_synthesis_diagnostics(out)
    assert diag["candidateCharCount"] == 5


def test_candidate_text_omitted() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="secret",
    )
    diag = build_synthesis_diagnostics(out)
    assert "candidateAnswerText" not in diag
    assert "secret" not in str(diag)


def test_raw_evidence_omitted() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="s", decision_summary="x")
    diag = build_synthesis_diagnostics(out)
    assert "evidenceItems" not in diag


def test_raw_context_omitted() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="s", decision_summary="x")
    diag = build_synthesis_diagnostics(out)
    assert "rawContext" not in diag


def test_raw_blocks_omitted() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="s", decision_summary="x")
    diag = build_synthesis_diagnostics(out)
    assert "blocks" not in diag


def test_no_chain_of_thought_fields() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="s", decision_summary="x")
    diag = build_synthesis_diagnostics(out)
    assert "chain_of_thought" not in diag


def test_compare_synthesis_to_live_response() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="long answer",
        uncertainty_notes=["maybe"],
        safe_to_show=True,
    )
    comparison = compare_synthesis_to_live_response(
        synthesis_output=out,
        live_response_summary={"textPreview": "short", "blockCount": 1},
    )
    assert comparison["candidateExists"] is True
    assert comparison["liveHasBlocks"] is True
