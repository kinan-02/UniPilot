"""Unit tests for clarification state schemas (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent.clarification.state_schemas import (
    PendingClarificationState,
    ResolvedClarificationState,
    sanitize_compact_context,
)


def test_pending_clarification_state_parses() -> None:
    now = datetime.now(timezone.utc)
    state = PendingClarificationState(
        clarification_id="clar_1",
        conversation_id="conv_1",
        original_user_message="Plan my semester",
        created_at=now,
        updated_at=now,
    )
    assert state.status == "pending"


def test_resolved_clarification_state_parses() -> None:
    resolved = ResolvedClarificationState(
        clarification_id="clar_1",
        conversation_id="conv_1",
        status="answered",
        answers=[{"need_id": "need-1", "value": "lighter workload", "provenance": "confirmed"}],
    )
    assert resolved.status == "answered"


def test_defaults_are_safe() -> None:
    now = datetime.now(timezone.utc)
    state = PendingClarificationState(
        clarification_id="clar_2",
        conversation_id="conv_2",
        original_user_message="hello",
        created_at=now,
        updated_at=now,
    )
    assert state.questions == []
    assert state.compact_context == {}


@pytest.mark.parametrize("forbidden_field", ["chain_of_thought", "scratchpad", "thoughts"])
def test_forbidden_chain_of_thought_fields_are_rejected(forbidden_field: str) -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="forbidden_clarification_state_field"):
        PendingClarificationState.model_validate(
            {
                "clarification_id": "clar_x",
                "conversation_id": "conv_x",
                "original_user_message": "hello",
                "created_at": now,
                "updated_at": now,
                forbidden_field: "secret",
            }
        )


def test_compact_context_rejects_forbidden_raw_keys() -> None:
    cleaned = sanitize_compact_context(
        {
            "compiled_context": {"secret": True},
            "questionCount": 1,
            "raw_context": "nope",
        }
    )
    assert cleaned == {"questionCount": 1}
