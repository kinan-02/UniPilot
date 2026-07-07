"""Clarification question selection policy (Phase 28.2)."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.clarification.schemas import ClarificationQuestion


@dataclass(frozen=True)
class ClarificationSelectionResult:
    selected_questions: list[ClarificationQuestion]
    deferred_question_count: int
    batching_enabled: bool
    max_questions_per_turn: int


def _compatible_for_batch(first: ClarificationQuestion, candidate: ClarificationQuestion) -> bool:
    if first.ambiguity_type != candidate.ambiguity_type:
        return False
    if first.consequence != candidate.consequence:
        return False
    return True


def select_clarification_questions(
    questions: list[ClarificationQuestion],
    *,
    batching_enabled: bool,
    max_questions_per_turn: int,
) -> ClarificationSelectionResult:
    """Select user-facing clarification questions with optional batching."""
    if not questions:
        return ClarificationSelectionResult(
            selected_questions=[],
            deferred_question_count=0,
            batching_enabled=batching_enabled,
            max_questions_per_turn=max_questions_per_turn,
        )

    if not batching_enabled:
        return ClarificationSelectionResult(
            selected_questions=list(questions[:1]),
            deferred_question_count=max(0, len(questions) - 1),
            batching_enabled=False,
            max_questions_per_turn=1,
        )

    limit = max(1, int(max_questions_per_turn))
    selected: list[ClarificationQuestion] = []
    for question in questions:
        if len(selected) >= limit:
            break
        if not selected or _compatible_for_batch(selected[0], question):
            selected.append(question)

    return ClarificationSelectionResult(
        selected_questions=selected,
        deferred_question_count=max(0, len(questions) - len(selected)),
        batching_enabled=True,
        max_questions_per_turn=limit,
    )
