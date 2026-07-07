"""Clarification state transitions and expiration (Phase 18)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agent.clarification.fallbacks import build_assumed_answer, build_assumption_record
from app.agent.clarification.schemas import ClarificationNeed
from app.agent.clarification.state_schemas import PendingClarificationState, ResolvedClarificationState


def should_expire_pending_state(state: PendingClarificationState, *, now: datetime | None = None) -> bool:
    current = _ensure_aware(now or datetime.now(timezone.utc))
    expires_at = _ensure_aware(state.expires_at)
    if expires_at is not None and expires_at <= current:
        return True
    return state.pending_turn_count > state.max_pending_turns


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_expired_resolution(state: PendingClarificationState) -> ResolvedClarificationState:
    assumed_answers: list[dict[str, Any]] = []
    assumptions: list[dict[str, Any]] = []
    warnings = ["clarification_expired"]

    for need_dict in state.needs:
        try:
            need = ClarificationNeed.model_validate(need_dict)
            assumed = build_assumed_answer(need)
            if assumed is not None:
                answer_dict = assumed.model_dump()
                assumed_answers.append(answer_dict)
                assumptions.append(build_assumption_record(need, assumed))
        except Exception:  # noqa: BLE001
            continue

    if assumed_answers:
        from app.agent.clarification.resume import build_resume_payload

        return ResolvedClarificationState(
            clarification_id=state.clarification_id,
            conversation_id=state.conversation_id,
            status="assumed",
            answers=assumed_answers,
            assumptions_created=assumptions,
            resume_payload=build_resume_payload(
                pending_state=state,
                answers=assumed_answers,
                assumptions_created=assumptions,
            ),
            warnings=[*warnings, "expired_with_fallback_assumptions"],
        )

    return ResolvedClarificationState(
        clarification_id=state.clarification_id,
        conversation_id=state.conversation_id,
        status="expired",
        warnings=warnings,
    )


def transition_status_after_resolution(resolved: ResolvedClarificationState) -> str:
    return resolved.status
