"""HTTP client for the one `api`-side internal endpoint retrieval needs.

Ported from `services/agent/app/clients/internal_api_client.py` -- only
`fetch_student_user_context` (used by `mongodb_user_retriever.py`). The
other functions there (graduation audit, semester-plan-options, requirement
contribution) belong to future Orchestrator/tool work, not retrieval.

Uses `X-Internal-Service-Token` -- never a user JWT.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

UNREACHABLE_DETAIL = "the plan service could not be reached"
"""What the DEFECT says when `api` does not answer at all.

Fixed text, because this detail is written into a defect message and a defect
message is shown to the model, which may quote it. httpx spells a refused
connection as `[Errno 111] Connect call failed ('10.0.3.7', 3000)`, and an
internal host and port is not something to hand a student.
"""


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
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=_headers(settings),
                json=json_body,
                params=params,
            )
    except httpx.HTTPError as exc:
        # `dispatch` catches InternalApiClientError and turns it into a DEFECT, so
        # the model can answer around a plan it could not get. An httpx exception
        # skips that handler and ends the whole run -- the student gets nothing
        # instead of the part that never needed a plan.
        logger.warning("api unreachable at %s: %s", url, exc)
        raise InternalApiClientError(status_code=503, detail=UNREACHABLE_DETAIL) from exc

    try:
        payload = response.json() if response.content else {}
    except ValueError as exc:
        logger.warning("api returned non-JSON (%s) from %s: %s", response.status_code, url, exc)
        raise InternalApiClientError(
            status_code=502, detail="api returned an invalid response"
        ) from exc

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


async def fetch_term_plan(
    *,
    user_id: str,
    semester_codes: list[str],
    candidates: list[dict[str, Any]],
    max_credits: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build a conflict-free term plan from agent-supplied candidates.

    Returns the endpoint's full result payload: `terms` (each with placedCourses,
    credits, weeklySchedule, examSummary), `unscheduled`, and `maxCredits`.
    """
    cfg = settings or get_settings()
    body: dict[str, Any] = {"semesterCodes": semester_codes, "candidates": candidates}
    if max_credits is not None:
        body["maxCredits"] = max_credits
    return await _request(
        "POST", f"/internal/term-plan/users/{user_id}", settings=cfg, json_body=body
    )
