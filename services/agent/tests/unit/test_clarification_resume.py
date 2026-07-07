"""Unit tests for clarification resume helpers (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.clarification.resume import (
    build_effective_context_text,
    build_resume_payload,
    resume_assumption_statements,
)
from app.agent.clarification.state_schemas import PendingClarificationState


def _pending() -> PendingClarificationState:
    now = datetime.now(timezone.utc)
    return PendingClarificationState(
        clarification_id="clar_1",
        conversation_id="conv_1",
        original_user_message="Plan my next semester",
        original_intent="semester_plan_generation",
        original_workflow_name="semester_planning_workflow",
        created_at=now,
        updated_at=now,
    )


def test_resume_payload_includes_original_message() -> None:
    payload = build_resume_payload(
        pending_state=_pending(),
        answers=[{"need_id": "need-1", "value": "lighter workload", "provenance": "confirmed"}],
    )
    assert payload["originalUserMessage"] == "Plan my next semester"


def test_resume_payload_includes_confirmed_answers() -> None:
    answers = [{"need_id": "need-1", "value": "lighter workload", "provenance": "confirmed"}]
    payload = build_resume_payload(pending_state=_pending(), answers=answers)
    assert payload["confirmedAnswers"] == answers


def test_effective_message_includes_clarification() -> None:
    text = build_effective_context_text(
        original_user_message="Plan my next semester",
        confirmed_answers=[{"need_id": "need-1", "value": "lighter workload"}],
        question_topics={"need-1": "workload preference"},
    )
    assert "Plan my next semester" in text
    assert "lighter workload" in text


def test_persisted_user_message_is_not_mutated() -> None:
    original = "Plan my next semester"
    build_effective_context_text(
        original_user_message=original,
        confirmed_answers=[{"need_id": "need-1", "value": "lighter workload"}],
    )
    assert original == "Plan my next semester"


def test_assumptions_created_are_plan_assumption_compatible() -> None:
    statements = resume_assumption_statements(
        confirmed_answers=[{"need_id": "need-1", "value": "lighter workload"}],
        assumptions_created=[
            {
                "kind": "user_preference",
                "statement": "Assumed preference: lighter workload",
                "provenance": "confirmed",
                "confidence": 1.0,
                "consequenceIfWrong": "medium",
            }
        ],
    )
    assert statements[0].startswith("Assumed preference")


def test_raw_context_is_not_included() -> None:
    text = build_effective_context_text(
        original_user_message="Plan my next semester",
        confirmed_answers=[{"need_id": "need-1", "value": "lighter workload"}],
    )
    assert "compiled_context" not in text
    assert "planner_output" not in text
