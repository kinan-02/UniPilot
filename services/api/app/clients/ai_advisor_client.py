"""HTTP client for the internal AI advisor service."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

UNAVAILABLE_DETAIL = "The advisor is temporarily unavailable. Please try again in a moment."
"""What the student is told when the AI service cannot be reached.

Deliberately fixed text. httpx spells a refused connection as
`[Errno 111] Connect call failed ('10.0.3.7', 3001)` -- an internal host and port,
which belongs in the log and not in a rendered answer.
"""


class AiAdvisorClientError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def ask_advisor(
    *,
    question: str,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    url = f"{settings.resolved_ai_service_url()}/advise"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(settings.ai_advisor_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json={"question": question, "user_id": user_id},
            )
    except httpx.HTTPError as exc:
        # The agent being down or slower than `ai_advisor_timeout_seconds` is an
        # ordinary production event, not an exception the route should turn into a
        # 500. 503 is what the caller already has a branch for.
        logger.warning("AI advisor unreachable at %s: %s", url, exc)
        raise AiAdvisorClientError(status_code=503, detail=UNAVAILABLE_DETAIL) from exc

    try:
        payload = response.json() if response.content else {}
    except ValueError as exc:
        # A proxy or gateway in front of the agent answers with HTML, not JSON.
        logger.warning("AI advisor returned non-JSON (%s): %s", response.status_code, exc)
        raise AiAdvisorClientError(
            status_code=502, detail="AI advisor returned an invalid response"
        ) from exc

    if response.status_code >= 400:
        detail = payload.get("error") if isinstance(payload, dict) else None
        if not detail and isinstance(payload, dict):
            detail = payload.get("detail")
        if not detail:
            detail = "AI advisor request failed"
        raise AiAdvisorClientError(status_code=response.status_code, detail=str(detail))

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise AiAdvisorClientError(
            status_code=502,
            detail="AI advisor returned an invalid response",
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise AiAdvisorClientError(
            status_code=502,
            detail="AI advisor response missing data",
        )

    return data

async def stream_advisor(
    *,
    question: str,
    user_id: str,
    settings: Settings | None = None,
) -> AsyncGenerator[str, None]:
    settings = settings or get_settings()
    url = f"{settings.resolved_ai_service_url()}/advise/stream"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(settings.ai_advisor_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json={"question": question, "user_id": user_id},
        ) as response:
            if response.status_code >= 400:
                raise AiAdvisorClientError(status_code=response.status_code, detail="Streaming request failed")
            async for chunk in response.aiter_text():
                yield chunk
