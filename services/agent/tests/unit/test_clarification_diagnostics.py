"""Unit tests for clarification diagnostics metadata (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.diagnostics import build_clarification_metadata
from app.agent.clarification.schemas import ClarificationCapabilityOutput, ClarificationQuestion


def test_compact_metadata_built() -> None:
    output = ClarificationCapabilityOutput(
        status="question_ready",
        questions=[
            ClarificationQuestion(
                id="q-1",
                need_id="need-1",
                prompt="Which do you prefer?",
                options=["a", "b"],
                consequence="high",
                ambiguity_type="preference",
            )
        ],
        diagnostics={"needCount": 1, "questionCount": 1, "assumedAnswerCount": 0},
    )
    metadata = build_clarification_metadata(output)
    assert metadata["status"] == "question_ready"
    assert metadata["needCount"] == 1


def test_questions_summarized_without_full_prompt() -> None:
    output = ClarificationCapabilityOutput(
        status="question_ready",
        questions=[
            ClarificationQuestion(
                id="q-1",
                need_id="need-1",
                prompt="Very long prompt that should not appear in metadata",
                consequence="high",
                ambiguity_type="preference",
            )
        ],
        diagnostics={"needCount": 1, "questionCount": 1},
    )
    metadata = build_clarification_metadata(output)
    summary = metadata["questions"][0]
    assert "prompt" not in summary
    assert summary["optionCount"] == 0


def test_assumptions_counted() -> None:
    output = ClarificationCapabilityOutput(
        status="assumed_default",
        assumptions_created=[{"kind": "user_preference", "provenance": "assumed"}],
        diagnostics={"assumedAnswerCount": 1},
    )
    metadata = build_clarification_metadata(output)
    assert metadata["assumptionsCreated"] == 1


def test_warnings_capped() -> None:
    output = ClarificationCapabilityOutput(
        status="skipped",
        warnings=[f"warning-{index}" for index in range(20)],
    )
    metadata = build_clarification_metadata(output)
    assert len(metadata["warnings"]) <= 8


def test_raw_evidence_omitted() -> None:
    output = ClarificationCapabilityOutput(
        status="skipped",
        diagnostics={"needCount": 1, "rawEvidence": {"secret": True}},
    )
    metadata = build_clarification_metadata(output)
    assert "rawEvidence" not in metadata


def test_raw_monitor_output_omitted() -> None:
    metadata = build_clarification_metadata(ClarificationCapabilityOutput(status="skipped"))
    assert "monitor" not in str(metadata).lower() or "monitorDecisionAction" not in metadata


def test_no_chain_of_thought_fields() -> None:
    metadata = build_clarification_metadata(ClarificationCapabilityOutput(status="skipped"))
    text = str(metadata).lower()
    for marker in ("chain_of_thought", "hidden_reasoning", "scratchpad", "thoughts"):
        assert marker not in text
