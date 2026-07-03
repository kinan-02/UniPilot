"""Resume MAS sessions after goal clarification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.agent_session_repository import (
    find_agent_session_by_id_and_user,
    to_public_agent_session,
    update_agent_session_by_id_and_user,
)
from app.services.agent_session_continuation_service import enqueue_existing_agent_session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _merge_goal_with_clarification(*, goal: str, clarification: str) -> str:
    base = goal.strip()
    detail = clarification.strip()
    if not base:
        return detail
    if not detail:
        return base
    return f"{base}\n\nClarification: {detail}"


async def clarify_agent_session(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    session_id: str,
    clarification: str,
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}

    if session.get("status") != "awaiting_clarification":
        return {
            "status": "invalid_state",
            "error": "Only sessions awaiting clarification can be clarified.",
        }

    detail = clarification.strip()
    if not detail:
        return {"status": "validation_error", "errors": ["Clarification cannot be empty."]}

    prior_transcript = list(session.get("transcript") or [])
    clarifications = list(session.get("clarifications") or [])
    clarifications.append(
        {
            "text": detail,
            "askedAt": session.get("updatedAt"),
            "answeredAt": _utc_now(),
        }
    )

    updated = await update_agent_session_by_id_and_user(
        database,
        session_id,
        user_id,
        {
            "goal": _merge_goal_with_clarification(goal=str(session.get("goal") or ""), clarification=detail),
            "status": "pending",
            "finalDecision": None,
            "utilityBreakdown": None,
            "error": None,
            "rounds": 0,
            "priorTranscript": prior_transcript,
            "clarifications": clarifications,
            "updatedAt": _utc_now(),
        },
    )
    if updated is None:
        return {"status": "not_found"}

    enqueued = await enqueue_existing_agent_session(database, session_id=session_id)
    public = to_public_agent_session(updated)
    if public is None:
        return {"status": "error", "error": "Failed to serialize agent session"}

    public["enqueued"] = enqueued
    return {"status": "ok", "session": public}
