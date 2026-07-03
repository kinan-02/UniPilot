"""Build advisor user context and call the internal AI service."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.ai_advisor_client import AiAdvisorClientError, ask_advisor
from app.config import Settings, get_settings
from app.services.student_user_context_service import build_student_user_context


async def build_advisor_user_context(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    context = await build_student_user_context(database, user_id)
    if "user_id" in context:
        return {key: value for key, value in context.items() if key != "user_id"}
    return context


async def ask_advisor_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    question: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    user_context = await build_advisor_user_context(database, user_id)
    try:
        raw = await ask_advisor(
            question=question,
            user_context=user_context,
            settings=settings,
        )
    except AiAdvisorClientError as exc:
        if exc.status_code == 503:
            return {"status": "unavailable", "detail": exc.detail}
        if exc.status_code == 400:
            return {"status": "bad_request", "detail": exc.detail}
        return {"status": "error", "detail": exc.detail}

    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    return {
        "status": "ok",
        "advisor": {
            "question": raw.get("question", question),
            "answer": response.get("answer", ""),
            "confidence": response.get("confidence", "medium"),
            "courseIds": response.get("course_ids", []),
            "wikiSlugs": response.get("wiki_slugs", []),
            "sources": response.get("sources", []),
            "contacts": response.get("contacts", []),
            "eligibility": response.get("eligibility"),
            "semesterResolution": raw.get("semester_resolution"),
            "retrievalStatus": (raw.get("retrieval_agent") or {}).get("status"),
        },
    }
