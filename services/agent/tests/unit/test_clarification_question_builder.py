"""Unit tests for clarification question builder and batching (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.policy import decide_clarification_action
from app.agent.clarification.question_builder import batch_clarification_questions, build_clarification_question
from app.agent.clarification.schemas import ClarificationNeed, ClarificationQuestion


def _need(**overrides) -> ClarificationNeed:
    base = {
        "id": "need-internal-id-12345678",
        "source": "planner",
        "ambiguity_type": "preference",
        "consequence": "high",
        "question_topic": "prioritize mandatory requirements or lighter workload",
        "reason": "missing_preference_context",
        "options": ["prioritize mandatory requirements", "keep workload lighter"],
    }
    base.update(overrides)
    return ClarificationNeed(**base)


def test_builds_concise_question() -> None:
    need = _need()
    decision = decide_clarification_action(need)
    question = build_clarification_question(need, decision)
    assert question is not None
    assert "preference" in question.prompt.lower()


def test_includes_options() -> None:
    need = _need()
    decision = decide_clarification_action(need)
    question = build_clarification_question(need, decision)
    assert question is not None
    assert len(question.options) == 2


def test_omits_internal_ids() -> None:
    need = _need()
    decision = decide_clarification_action(need)
    question = build_clarification_question(need, decision)
    assert question is not None
    assert need.id not in question.prompt


def test_omits_raw_evidence() -> None:
    need = _need(evidence={"missingContextSnippet": "secret raw evidence"})
    decision = decide_clarification_action(need)
    question = build_clarification_question(need, decision)
    assert question is not None
    assert "secret raw evidence" not in question.prompt


def test_returns_none_when_decision_is_not_ask_user() -> None:
    need = _need(consequence="low", default_assumption="lighter workload")
    decision = decide_clarification_action(need)
    assert build_clarification_question(need, decision) is None


def test_question_text_has_no_chain_of_thought_markers() -> None:
    need = _need()
    decision = decide_clarification_action(need)
    question = build_clarification_question(need, decision)
    assert question is not None
    lowered = question.prompt.lower()
    for marker in ("chain_of_thought", "hidden_reasoning", "scratchpad", "thoughts"):
        assert marker not in lowered


def test_batch_caps_to_max_questions() -> None:
    questions = [
        ClarificationQuestion(
            id=f"q-{index}",
            need_id=f"need-{index}",
            prompt=f"Question {index}",
            consequence="medium",
            ambiguity_type="preference",
        )
        for index in range(5)
    ]
    batched, warnings = batch_clarification_questions(questions, max_questions=3)
    assert len(batched) == 3
    assert "clarification_questions_capped" in warnings


def test_batch_prioritizes_high_consequence() -> None:
    questions = [
        ClarificationQuestion(
            id="q-low",
            need_id="need-low",
            prompt="low question",
            consequence="low",
            ambiguity_type="preference",
        ),
        ClarificationQuestion(
            id="q-high",
            need_id="need-high",
            prompt="high question",
            consequence="high",
            ambiguity_type="preference",
        ),
    ]
    batched, _ = batch_clarification_questions(questions, max_questions=1)
    assert batched[0].consequence == "high"


def test_batch_deduplicates_same_topic() -> None:
    questions = [
        ClarificationQuestion(
            id="q-1",
            need_id="need-1",
            prompt="Same topic?",
            consequence="medium",
            ambiguity_type="preference",
        ),
        ClarificationQuestion(
            id="q-2",
            need_id="need-2",
            prompt="same topic?",
            consequence="high",
            ambiguity_type="preference",
        ),
    ]
    batched, _ = batch_clarification_questions(questions, max_questions=3)
    assert len(batched) == 1


def test_batch_preserves_deterministic_order() -> None:
    questions = [
        ClarificationQuestion(
            id="q-a",
            need_id="need-a",
            prompt="Alpha topic",
            consequence="high",
            ambiguity_type="preference",
        ),
        ClarificationQuestion(
            id="q-b",
            need_id="need-b",
            prompt="Beta topic",
            consequence="high",
            ambiguity_type="preference",
        ),
    ]
    first, _ = batch_clarification_questions(questions, max_questions=3)
    second, _ = batch_clarification_questions(questions, max_questions=3)
    assert [item.id for item in first] == [item.id for item in second]
