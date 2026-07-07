"""Unit tests for synthesis schemas (Phase 21)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.synthesis.schemas import (
    EvidenceItem,
    SynthesisConflict,
    SynthesisInput,
    SynthesisOutput,
)


def test_evidence_item_parses() -> None:
    item = EvidenceItem(
        id="ev-1",
        source_type="deterministic_workflow",
        source_name="graduation_progress_workflow",
        claim="You need 3 more credits.",
        trust_level="authoritative",
    )
    assert item.confidence == 0.5


def test_synthesis_conflict_parses() -> None:
    conflict = SynthesisConflict(id="c-1", severity="warning", summary="Mismatch")
    assert conflict.resolution == "unresolved"


def test_synthesis_input_parses() -> None:
    inp = SynthesisInput(synthesis_id="syn-1")
    assert inp.evidence_items == []


def test_synthesis_output_parses() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="syn-1", decision_summary="skipped")
    assert out.safe_to_promote is False


def test_defaults_are_safe() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="syn-1", decision_summary="skipped")
    assert out.safe_to_show is False
    assert out.safe_to_promote is False


def test_requested_next_step_defaults_to_none() -> None:
    out = SynthesisOutput(status="skipped", synthesis_id="syn-1", decision_summary="skipped")
    assert out.requested_next_step is None


def test_requested_next_step_accepts_ask_clarification() -> None:
    out = SynthesisOutput(
        status="needs_clarification",
        synthesis_id="syn-1",
        decision_summary="needs clarification",
        requested_next_step="ask_clarification",
    )
    assert out.requested_next_step == "ask_clarification"


def test_requested_next_step_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        SynthesisOutput(
            status="skipped",
            synthesis_id="syn-1",
            decision_summary="skipped",
            requested_next_step="do_something_unsupported",
        )


def test_forbidden_chain_of_thought_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(
            {
                "id": "ev-1",
                "source_type": "unknown",
                "source_name": "x",
                "claim": "x",
                "trust_level": "low",
                "chain_of_thought": "secret",
            }
        )
