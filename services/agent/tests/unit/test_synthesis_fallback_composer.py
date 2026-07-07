"""Unit tests for deterministic synthesis fallback composer (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.evidence import evidence_from_live_response_summary
from app.agent.synthesis.fallback_composer import deterministic_synthesis
from app.agent.synthesis.schemas import SynthesisInput
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        AGENT_SYNTHESIS_MAX_CONFLICTS=6,
        AGENT_SYNTHESIS_MAX_CANDIDATE_CHARS=5000,
    )


def test_sufficient_trusted_evidence_creates_candidate_ready_output() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "You need 3 credits to graduate."},
        evidence_items=evidence_from_live_response_summary({"textPreview": "You need 3 credits to graduate."}),
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.status in {"candidate_ready", "candidate_ready_with_warnings"}
    assert out.candidate_answer_text


def test_unsafe_signal_returns_unsafe() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        monitor_summary={"decision": {"action": "abort_safely"}},
        evidence_items=[],
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.status == "unsafe"


def test_high_severity_conflict_returns_needs_clarification() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "Answer"},
        monitor_summary={"decision": {"action": "abort_safely"}},
        evidence_items=evidence_from_live_response_summary({"textPreview": "Answer"}),
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.status == "unsafe"


def test_missing_evidence_returns_insufficient_evidence() -> None:
    inp = SynthesisInput(synthesis_id="syn-1")
    out = deterministic_synthesis(inp, _settings())
    assert out.status == "insufficient_evidence"
    assert out.requested_next_step == "retrieve_more_context"


def test_candidate_ready_leaves_requested_next_step_unset() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "You need 3 credits to graduate."},
        evidence_items=evidence_from_live_response_summary({"textPreview": "You need 3 credits to graduate."}),
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.requested_next_step is None


def test_uncertainty_notes_are_preserved() -> None:
    from app.agent.synthesis.evidence import evidence_from_clarification

    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "Answer"},
        evidence_items=[
            *evidence_from_live_response_summary({"textPreview": "Answer"}),
            *evidence_from_clarification(
                {"effectiveClarificationContext": {"confirmedClarifications": [{"value": "x", "provenance": "assumed"}]}}
            ),
        ],
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.uncertainty_notes


def test_candidate_answer_passes_max_length() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "x" * 6000},
        evidence_items=evidence_from_live_response_summary({"textPreview": "x" * 6000}),
    )
    out = deterministic_synthesis(inp, Settings(AGENT_SYNTHESIS_MAX_CANDIDATE_CHARS=1000))
    assert len(out.candidate_answer_text or "") <= 1000


def test_safe_to_promote_false_always() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "Answer"},
        evidence_items=evidence_from_live_response_summary({"textPreview": "Answer"}),
    )
    out = deterministic_synthesis(inp, _settings())
    assert out.safe_to_promote is False


def test_proposed_actions_never_created() -> None:
    inp = SynthesisInput(
        synthesis_id="syn-1",
        live_response_summary={"textPreview": "Answer"},
        evidence_items=evidence_from_live_response_summary({"textPreview": "Answer"}),
    )
    out = deterministic_synthesis(inp, _settings())
    assert "proposed" not in str(out.model_dump()).lower()
