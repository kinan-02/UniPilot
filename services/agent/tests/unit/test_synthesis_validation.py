"""Unit tests for synthesis validation (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput
from app.agent.synthesis.validation import validate_synthesis_output
from app.config import Settings


def _settings() -> Settings:
    return Settings(AGENT_SYNTHESIS_MAX_CANDIDATE_CHARS=100)


def test_empty_candidate_downgraded() -> None:
    out = SynthesisOutput(status="candidate_ready", synthesis_id="s", decision_summary="x", candidate_answer_text="")
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.status == "insufficient_evidence"


def test_too_long_candidate_downgraded() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="x" * 200,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert len(validated.candidate_answer_text or "") <= 100


def test_write_claim_rejected() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="I saved your plan.",
        safe_to_show=True,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.status == "unsafe"


def test_proposed_action_claim_rejected() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="Created proposed action for import.",
        safe_to_show=True,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.status == "unsafe"


def test_chain_of_thought_marker_rejected() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="chain_of_thought: secret",
        safe_to_show=True,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.status == "failed"


def test_raw_payload_marker_rejected() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="Here is retrievalMetadata dump",
        safe_to_show=True,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.safe_to_show is False


def test_unsafe_monitor_conflict_blocks_safe_to_show() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="Answer",
        safe_to_show=True,
    )
    inp = SynthesisInput(synthesis_id="s", monitor_summary={"decision": {"action": "abort_safely"}})
    validated = validate_synthesis_output(out, inp, _settings())
    assert validated.safe_to_show is False


def test_safe_to_promote_forced_false() -> None:
    out = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="s",
        decision_summary="x",
        candidate_answer_text="Answer",
        safe_to_promote=True,
    )
    validated = validate_synthesis_output(out, SynthesisInput(synthesis_id="s"), _settings())
    assert validated.safe_to_promote is False
