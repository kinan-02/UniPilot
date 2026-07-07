"""Resume payload and effective context for clarified turns (Phase 18)."""

from __future__ import annotations

from typing import Any

from app.agent.clarification.state_schemas import PendingClarificationState


def build_resume_payload(
    *,
    pending_state: PendingClarificationState,
    answers: list[dict[str, Any]],
    assumptions_created: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "originalUserMessage": pending_state.original_user_message,
        "originalIntent": pending_state.original_intent,
        "originalWorkflowName": pending_state.original_workflow_name,
        "originalPlanId": pending_state.original_plan_id,
        "confirmedAnswers": answers,
        "assumptionsCreated": list(assumptions_created or []),
        "resumeMode": pending_state.resume_mode,
    }


def build_effective_context_text(
    *,
    original_user_message: str,
    confirmed_answers: list[dict[str, Any]],
    question_topics: dict[str, str] | None = None,
) -> str:
    """Internal effective prompt for task understanding/planning only."""
    lines = [f"Original request:\n{original_user_message.strip()}", "", "Confirmed clarification:"]
    topics = question_topics or {}
    for answer in confirmed_answers:
        need_id = str(answer.get("need_id") or answer.get("needId") or "")
        topic = topics.get(need_id) or "preference"
        value = str(answer.get("value") or "").strip()
        lines.append(f"- {topic}: {value}")
    return "\n".join(lines)


def build_effective_clarification_context(
    *,
    original_user_message: str,
    confirmed_answers: list[dict[str, Any]],
    assumptions_created: list[dict[str, Any]] | None = None,
    question_topics: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compact structured effective context for planning/task understanding (Phase 19)."""
    topics = question_topics or {}
    confirmed_clarifications: list[dict[str, Any]] = []
    for answer in confirmed_answers or []:
        if not isinstance(answer, dict):
            continue
        need_id = str(answer.get("need_id") or answer.get("needId") or "")
        topic = str(answer.get("topic") or topics.get(need_id) or "semester planning preference")
        value = str(answer.get("value") or "").strip()
        if not value:
            continue
        confirmed_clarifications.append(
            {
                "topic": topic[:120],
                "value": value[:240],
                "provenance": str(answer.get("provenance") or "confirmed"),
                "confidence": float(answer.get("confidence") or 1.0),
            }
        )

    compact_assumptions: list[dict[str, Any]] = []
    for record in assumptions_created or []:
        if not isinstance(record, dict):
            continue
        compact_assumptions.append(
            {
                "kind": str(record.get("kind") or "user_preference"),
                "provenance": str(record.get("provenance") or "confirmed"),
                "confidence": float(record.get("confidence") or 1.0),
            }
        )

    return {
        "originalUserMessage": (original_user_message or "").strip()[:500],
        "confirmedClarifications": confirmed_clarifications[:12],
        "assumptionsCreated": compact_assumptions[:12],
    }


def resume_assumption_statements(
    *,
    confirmed_answers: list[dict[str, Any]],
    assumptions_created: list[dict[str, Any]] | None = None,
) -> list[str]:
    statements: list[str] = []
    for record in assumptions_created or []:
        statement = str(record.get("statement") or "").strip()
        if statement:
            statements.append(statement)
    if statements:
        return statements

    for answer in confirmed_answers:
        value = str(answer.get("value") or "").strip()
        if value:
            statements.append(f"Confirmed preference: {value}")
    return statements
