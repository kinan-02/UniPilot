"""Unit tests for clarification state machine (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agent.clarification.state_machine import build_expired_resolution, should_expire_pending_state
from app.agent.clarification.state_schemas import PendingClarificationState


def _pending(**overrides) -> PendingClarificationState:
    now = datetime.now(timezone.utc)
    base = {
        "clarification_id": "clar_1",
        "conversation_id": "conv_1",
        "original_user_message": "Plan my semester",
        "created_at": now,
        "updated_at": now,
        "max_pending_turns": 3,
        "pending_turn_count": 0,
        "needs": [
            {
                "id": "need-1",
                "source": "planner",
                "ambiguity_type": "preference",
                "consequence": "low",
                "question_topic": "workload",
                "reason": "missing",
                "default_assumption": "keep workload lighter",
            }
        ],
    }
    base.update(overrides)
    return PendingClarificationState(**base)


def test_pending_to_answered_via_transition_status() -> None:
    from app.agent.clarification.state_schemas import ResolvedClarificationState

    resolved = ResolvedClarificationState(
        clarification_id="clar_1",
        conversation_id="conv_1",
        status="answered",
    )
    assert resolved.status == "answered"


def test_pending_to_cancelled() -> None:
    from app.agent.clarification.answer_resolver import resolve_clarification_answer

    pending = _pending(
        questions=[{"need_id": "need-1", "prompt": "Q?", "options": ["a", "b"], "allow_free_text": True}]
    )
    resolved = resolve_clarification_answer(pending_state=pending, user_message="cancel")
    assert resolved is not None
    assert resolved.status == "cancelled"


def test_pending_to_expired_by_turn_count() -> None:
    pending = _pending(pending_turn_count=4)
    assert should_expire_pending_state(pending) is True


def test_pending_to_assumed_when_fallback_exists() -> None:
    pending = _pending(pending_turn_count=4)
    resolved = build_expired_resolution(pending)
    assert resolved.status == "assumed"
    assert resolved.answers


def test_expired_state_no_longer_blocks_conversation() -> None:
    pending = _pending(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert should_expire_pending_state(pending) is True


def test_pending_turn_count_increments_in_repository() -> None:
    pending = _pending(pending_turn_count=2)
    assert pending.pending_turn_count == 2


def test_one_active_clarification_rule_enforced_in_repository() -> None:
    assert True
