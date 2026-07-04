"""Advisor conversation history (summarized, user-owned)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.ai_advisor_client import AiAdvisorClientError, summarize_conversation
from app.config import Settings, get_settings
from app.repositories.advisor_conversation_repository import (
    create_advisor_conversation,
    find_advisor_conversation_for_user,
    list_advisor_conversations_for_user,
    to_public_advisor_conversation,
    update_advisor_conversation_summary,
)


def _fallback_summary_update(
    previous_summary: str | None,
    user_message: str,
    advisor_answer: str,
) -> dict[str, str]:
    user_line = " ".join(user_message.split())[:240]
    answer_line = " ".join(advisor_answer.split())[:400]
    title = user_line[:72] + ("…" if len(user_line) > 72 else "") or "Advisor chat"
    if previous_summary and previous_summary.strip():
        summary = (
            f"{previous_summary.strip()}\n\n"
            f"Latest — Student: {user_line}\n"
            f"Advisor: {answer_line}"
        )
    else:
        summary = f"Student: {user_line}\nAdvisor: {answer_line}"
    return {"title": title, "summary": summary[:4000]}


async def _summarize_exchange(
    *,
    previous_summary: str | None,
    user_message: str,
    advisor_answer: str,
    settings: Settings,
) -> dict[str, str]:
    try:
        return await summarize_conversation(
            user_message=user_message,
            advisor_answer=advisor_answer,
            previous_summary=previous_summary,
            settings=settings,
        )
    except AiAdvisorClientError:
        return _fallback_summary_update(previous_summary, user_message, advisor_answer)


async def list_conversations_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 30,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    result = await list_advisor_conversations_for_user(
        database,
        user_id,
        page=page,
        limit=limit,
        settings=settings,
    )
    conversations = [
        item
        for item in (
            to_public_advisor_conversation(doc) for doc in result["conversations"]
        )
        if item is not None
    ]
    return {
        "conversations": conversations,
        "pagination": {
            "total": result["total"],
            "page": result["page"],
            "limit": result["limit"],
        },
    }


async def get_conversation_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    conversation_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    document = await find_advisor_conversation_for_user(
        database,
        user_id,
        conversation_id,
        settings=settings,
    )
    public = to_public_advisor_conversation(document)
    if not public:
        return None
    return {"conversation": public}


async def persist_advisor_exchange(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    question: str,
    answer: str,
    confidence: str,
    conversation_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Create or update a summarized conversation after a successful advisor reply."""
    settings = settings or get_settings()
    previous_summary: str | None = None

    if conversation_id:
        existing = await find_advisor_conversation_for_user(
            database,
            user_id,
            conversation_id,
            settings=settings,
        )
        if not existing:
            return {"status": "conversation_not_found"}
        previous_summary = str(existing.get("summary") or "")

    summary_payload = await _summarize_exchange(
        previous_summary=previous_summary,
        user_message=question,
        advisor_answer=answer,
        settings=settings,
    )

    if conversation_id:
        updated = await update_advisor_conversation_summary(
            database,
            user_id,
            conversation_id,
            title=summary_payload["title"],
            summary=summary_payload["summary"],
            last_confidence=confidence,
            settings=settings,
        )
        public = to_public_advisor_conversation(updated)
        if not public:
            return {"status": "conversation_not_found"}
        return {"status": "ok", "conversation": public}

    created = await create_advisor_conversation(
        database,
        user_id,
        title=summary_payload["title"],
        summary=summary_payload["summary"],
        last_confidence=confidence,
        settings=settings,
    )
    public = to_public_advisor_conversation(created)
    return {"status": "ok", "conversation": public}
