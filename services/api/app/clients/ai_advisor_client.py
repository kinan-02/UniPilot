"""HTTP client for the internal AI advisor service."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class AiAdvisorClientError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def ask_advisor(
    *,
    question: str,
    user_context: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    url = f"{settings.resolved_ai_service_url()}/advise"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(settings.ai_advisor_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers=headers,
            json={"question": question, "user_context": user_context},
        )

    payload = response.json() if response.content else {}
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
