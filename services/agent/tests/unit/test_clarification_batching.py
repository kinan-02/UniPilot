"""Unit tests for clarification batching policy (Phase 28.2)."""

from __future__ import annotations

from app.agent.clarification.question_selection import select_clarification_questions
from app.agent.clarification.schemas import ClarificationQuestion


def _question(question_id: str, *, ambiguity: str = "preference", consequence: str = "medium") -> ClarificationQuestion:
    return ClarificationQuestion(
        id=question_id,
        need_id=f"need-{question_id}",
        prompt=f"Question {question_id}?",
        ambiguity_type=ambiguity,  # type: ignore[arg-type]
        consequence=consequence,  # type: ignore[arg-type]
    )


def test_batching_disabled_selects_only_one_question() -> None:
    questions = [_question("q1"), _question("q2"), _question("q3")]
    result = select_clarification_questions(questions, batching_enabled=False, max_questions_per_turn=3)
    assert len(result.selected_questions) == 1
    assert result.deferred_question_count == 2
    assert result.batching_enabled is False


def test_batching_enabled_selects_up_to_n_compatible_questions() -> None:
    questions = [_question("q1"), _question("q2"), _question("q3")]
    result = select_clarification_questions(questions, batching_enabled=True, max_questions_per_turn=2)
    assert len(result.selected_questions) == 2
    assert result.deferred_question_count == 1
    assert result.batching_enabled is True


def test_max_questions_respected() -> None:
    questions = [_question(f"q{i}") for i in range(5)]
    result = select_clarification_questions(questions, batching_enabled=True, max_questions_per_turn=3)
    assert len(result.selected_questions) == 3
    assert result.deferred_question_count == 2


def test_incompatible_questions_are_not_batched_together() -> None:
    questions = [
        _question("q1", ambiguity="preference"),
        _question("q2", ambiguity="epistemic"),
    ]
    result = select_clarification_questions(questions, batching_enabled=True, max_questions_per_turn=3)
    assert len(result.selected_questions) == 1
    assert result.deferred_question_count == 1
