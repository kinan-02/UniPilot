"""HTTP client for the one `api`-side internal endpoint retrieval needs.

Ported from `services/agent/app/clients/internal_api_client.py` -- only
`fetch_student_user_context` (used by `mongodb_user_retriever.py`). The
other functions there (graduation audit, semester-plan-options, requirement
contribution) belong to future Orchestrator/tool work, not retrieval.

Uses `X-Internal-Service-Token` -- never a user JWT.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class InternalApiClientError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Internal-Service-Token": settings.resolved_internal_service_token(),
    }


async def _request(
    method: str,
    path: str,
    *,
    settings: Settings,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{settings.resolved_api_service_url()}{path}"
    timeout = httpx.Timeout(settings.internal_api_timeout_seconds, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=_headers(settings),
            json=json_body,
            params=params,
        )

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = "api internal request failed"
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or payload.get("error") or detail)
        raise InternalApiClientError(status_code=response.status_code, detail=detail)

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise InternalApiClientError(status_code=502, detail="api returned an invalid response")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise InternalApiClientError(status_code=502, detail="api response missing data")
    return data


async def fetch_student_user_context(*, user_id: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    data = await _request("GET", f"/internal/user-context/users/{user_id}", settings=cfg)
    return data["userContext"]
