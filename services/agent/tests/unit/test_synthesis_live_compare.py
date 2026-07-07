"""Unit tests for synthesis live compare (Phase 22)."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.synthesis.live_compare import compare_synthesis_candidate_to_live_response
from app.agent.synthesis.schemas import SynthesisConflict, SynthesisOutput


def _live(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Short live answer.",
        blocks=[StructuredBlock(type="GraduationStatusBlock", data={"creditsRemaining": 40.0})],
        warnings=["data incomplete"],
        proposed_actions=[],
        used_sources=["catalog"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _synthesis(**overrides) -> SynthesisOutput:
    defaults = dict(
        status="candidate_ready",
        synthesis_id="syn-1",
        decision_summary="composed",
        uncertainty_notes=["maybe"],
        conflicts=[SynthesisConflict(id="c1", severity="warning", summary="warn")],
    )
    defaults.update(overrides)
    return SynthesisOutput(**defaults)


def test_returns_candidate_and_live_char_counts() -> None:
    result = compare_synthesis_candidate_to_live_response(
        candidate_text="A longer synthesis candidate answer.",
        live_response=_live(),
        synthesis_output=_synthesis(),
    )
    assert result["candidateCharCount"] > 0
    assert result["liveTextCharCount"] > 0


def test_detects_live_blocks_present() -> None:
    result = compare_synthesis_candidate_to_live_response(
        candidate_text="Candidate",
        live_response=_live(),
        synthesis_output=_synthesis(),
    )
    assert result["liveHasBlocks"] is True


def test_detects_live_proposed_actions() -> None:
    action = ProposedAction(id="a1", action_type="import_transcript", label="Import", payload={})
    result = compare_synthesis_candidate_to_live_response(
        candidate_text="Candidate",
        live_response=_live(proposed_actions=[action]),
        synthesis_output=_synthesis(),
    )
    assert result["liveProposedActionCount"] == 1


def test_summarizes_conflict_count() -> None:
    result = compare_synthesis_candidate_to_live_response(
        candidate_text="Candidate",
        live_response=_live(),
        synthesis_output=_synthesis(),
    )
    assert result["synthesisConflictCount"] == 1


def test_does_not_include_candidate_text() -> None:
    candidate = "Secret candidate text"
    result = compare_synthesis_candidate_to_live_response(
        candidate_text=candidate,
        live_response=_live(),
        synthesis_output=_synthesis(),
    )
    assert candidate not in str(result)


def test_does_not_include_live_text() -> None:
    live = _live(text="Secret live answer")
    result = compare_synthesis_candidate_to_live_response(
        candidate_text="Candidate",
        live_response=live,
        synthesis_output=_synthesis(),
    )
    assert "Secret live answer" not in str(result)
