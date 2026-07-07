"""HTTP client for the handful of `api`-side endpoints the agent service still needs.

The agent service has its own direct (mostly read-only) MongoDB connection
for simple lookups — see `app/repositories/` and `app/db/mongo.py`. These
calls are only for computation that intentionally stays exclusively in
`api` to avoid duplicating complex, actively-evolving business rules that
are also used by `api`'s own plain REST endpoints:

- graduation audit (`graduation_progress_calculator` + `graduation_audit_service`)
- semester plan generation (`semester_planning_service` + the planning engine)
- requirement contribution (`graduation_progress_calculator` pool/matrix rules)
- canonical per-student context summary (already exposed for `worker`/`ai`)

All calls use `X-Internal-Service-Token` — never a user JWT (the agent
service never receives or needs one).
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


async def fetch_graduation_audit(*, user_id: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    data = await _request(
        "GET", f"/internal/agent/graduation-audit/users/{user_id}", settings=cfg
    )
    return data["graduationAudit"]


async def fetch_semester_plan_options(
    *,
    user_id: str,
    context_snapshot: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    data = await _request(
        "POST",
        f"/internal/agent/semester-plan-options/users/{user_id}",
        settings=cfg,
        json_body=context_snapshot,
    )
    return data["semesterPlanning"]


async def fetch_course_requirement_contribution(
    *,
    program_code: str,
    course_number: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    return await _request(
        "GET",
        "/internal/agent/course-requirement-contribution",
        settings=cfg,
        params={"programCode": program_code, "courseNumber": course_number},
    )


async def fetch_student_user_context(*, user_id: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    data = await _request("GET", f"/internal/user-context/users/{user_id}", settings=cfg)
    return data["userContext"]
