"""Call the internal AI service on behalf of a student."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.ai_advisor_client import (
    UNAVAILABLE_DETAIL,
    AiAdvisorClientError,
    ask_advisor,
    stream_advisor,
)
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _error_event(detail: str) -> str:
    """The one shape `/advise/stream` already uses for a failure it survives.

    See `services/ai/app/routes/advise.py` -- the agent deliberately answers a
    mid-run failure with `{"type": "error"}` rather than a 500, because by then
    the 200 and the `text/event-stream` headers are long gone. This keeps that
    promise across the proxy, where the transport can fail just as easily.
    """
    return f"data: {json.dumps({'type': 'error', 'error': detail})}\n\n"


async def ask_advisor_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    question: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        raw = await ask_advisor(
            question=question,
            user_id=user_id,
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
            "courses": response.get("courses", []),
            "wikiSlugs": response.get("wiki_slugs", []),
            "sources": response.get("sources", []),
            "contacts": response.get("contacts", []),
            "eligibility": response.get("eligibility"),
            "semesterResolution": raw.get("semester_resolution"),
            "retrievalStatus": (raw.get("retrieval_agent") or {}).get("status"),
        },
    }

async def stream_advisor_for_user(
    user_id: str,
    question: str,
    *,
    settings: Settings | None = None,
) -> Any:
    settings = settings or get_settings()
    try:
        async for chunk in stream_advisor(
            question=question,
            user_id=user_id,
            settings=settings,
        ):
            yield chunk
    except (httpx.HTTPError, AiAdvisorClientError) as exc:
        # Whatever the agent already streamed stays on screen; this is appended to
        # it, so a run that dies halfway says so instead of just stopping.
        logger.warning("AI advisor stream failed for user %s: %s", user_id, exc)
        yield _error_event(UNAVAILABLE_DETAIL)
