"""Unit tests for clarification answer resolver (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.clarification.answer_resolver import resolve_clarification_answer
from app.agent.clarification.state_schemas import PendingClarificationState


def _pending(**overrides) -> PendingClarificationState:
    now = datetime.now(timezone.utc)
    base = {
        "clarification_id": "clar_1",
        "conversation_id": "conv_1",
        "original_user_message": "Plan my semester",
        "created_at": now,
        "updated_at": now,
        "questions": [
            {
                "need_id": "need-1",
                "prompt": "Which preference?",
                "options": ["prioritize mandatory requirements", "keep workload lighter"],
                "allow_free_text": True,
                "consequence": "high",
                "ambiguity_type": "preference",
            }
        ],
        "needs": [
            {
                "id": "need-1",
                "source": "planner",
                "ambiguity_type": "preference",
                "consequence": "high",
                "question_topic": "workload vs requirements",
                "reason": "missing_preference_context",
            }
        ],
    }
    base.update(overrides)
    return PendingClarificationState(**base)


def test_exact_option_text_resolves() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="keep workload lighter",
    )
    assert resolved is not None
    assert resolved.status == "answered"
    assert resolved.answers[0]["value"] == "keep workload lighter"


def test_numeric_option_resolves() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="2",
    )
    assert resolved is not None
    assert resolved.answers[0]["value"] == "keep workload lighter"


def test_first_second_resolves() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="first",
    )
    assert resolved is not None
    assert resolved.answers[0]["value"] == "prioritize mandatory requirements"


def test_free_text_resolves_for_one_question() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="lighter semester please",
    )
    assert resolved is not None
    assert resolved.answers[0]["provenance"] == "confirmed"


def test_incomplete_multi_question_answer_returns_unresolved() -> None:
    pending = _pending(
        questions=[
            {
                "need_id": "need-1",
                "prompt": "Q1?",
                "options": ["a", "b"],
                "allow_free_text": False,
            },
            {
                "need_id": "need-2",
                "prompt": "Q2?",
                "options": ["c", "d"],
                "allow_free_text": False,
            },
        ]
    )
    assert resolve_clarification_answer(pending_state=pending, user_message="a") is None


def test_cancel_phrase_cancels() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="never mind",
    )
    assert resolved is not None
    assert resolved.status == "cancelled"


def test_unrelated_question_unresolved() -> None:
    assert (
        resolve_clarification_answer(
            pending_state=_pending(),
            user_message="What are my graduation requirements?",
        )
        is None
    )


def test_ambiguous_answer_unresolved() -> None:
    pending = _pending(
        questions=[
            {
                "need_id": "need-1",
                "prompt": "Choose",
                "options": ["alpha", "beta"],
                "allow_free_text": False,
            }
        ]
    )
    assert resolve_clarification_answer(pending_state=pending, user_message="maybe") is None


def test_resolved_answers_have_provenance_confirmed() -> None:
    resolved = resolve_clarification_answer(
        pending_state=_pending(),
        user_message="1",
    )
    assert resolved is not None
    assert resolved.answers[0]["provenance"] == "confirmed"
    assert resolved.answers[0]["confidence"] == 1.0


def test_resolver_never_raises_on_malformed_state() -> None:
    broken = PendingClarificationState.model_construct(
        clarification_id="x",
        conversation_id="y",
        original_user_message="z",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        questions=[],
    )
    assert resolve_clarification_answer(pending_state=broken, user_message="hello") is None
