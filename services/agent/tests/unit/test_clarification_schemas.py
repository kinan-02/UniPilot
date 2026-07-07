"""Unit tests for clarification schemas (Phase 17)."""

from __future__ import annotations

import pytest

from app.agent.clarification.schemas import (
    ClarificationAnswer,
    ClarificationCapabilityOutput,
    ClarificationDecision,
    ClarificationNeed,
    ClarificationQuestion,
)


def test_clarification_need_parses() -> None:
    need = ClarificationNeed(
        id="need-1",
        source="monitor",
        ambiguity_type="preference",
        consequence="high",
        question_topic="workload vs requirements",
        reason="missing_preference_context",
    )
    assert need.source == "monitor"


def test_clarification_decision_parses() -> None:
    decision = ClarificationDecision(
        need_id="need-1",
        action="ask_user",
        reason="preference_high_consequence",
        confidence=0.85,
    )
    assert decision.action == "ask_user"


def test_clarification_question_parses() -> None:
    question = ClarificationQuestion(
        id="q-1",
        need_id="need-1",
        prompt="Which do you prefer?",
        consequence="high",
        ambiguity_type="preference",
    )
    assert question.allow_free_text is True


def test_clarification_answer_parses() -> None:
    answer = ClarificationAnswer(
        need_id="need-1",
        value="prioritize mandatory requirements",
        provenance="assumed",
        source="fallback",
        confidence=0.45,
    )
    assert answer.provenance == "assumed"


def test_clarification_capability_output_parses() -> None:
    output = ClarificationCapabilityOutput(status="skipped")
    assert output.questions == []


def test_defaults_are_safe() -> None:
    need = ClarificationNeed(
        id="need-2",
        source="planner",
        ambiguity_type="epistemic",
        consequence="low",
        question_topic="catalog detail",
        reason="missing_context",
    )
    assert need.options == []
    assert need.evidence == {}


@pytest.mark.parametrize(
    "forbidden_field",
    ["chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"],
)
def test_forbidden_chain_of_thought_fields_are_absent(forbidden_field: str) -> None:
    with pytest.raises(ValueError, match="forbidden_clarification_field"):
        ClarificationNeed.model_validate(
            {
                "id": "need-x",
                "source": "manual",
                "ambiguity_type": "unknown",
                "consequence": "low",
                "question_topic": "topic",
                "reason": "reason",
                forbidden_field: "secret",
            }
        )
