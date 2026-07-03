"""HTTP client for internal API graduation progress."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class GraduationProgressClientError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _extract_error_detail(payload: dict[str, Any], response: httpx.Response) -> str:
    detail = payload.get("detail") or payload.get("error") or response.text
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail)
    return str(detail or "")


def graduation_error_code(*, status_code: int, detail: str) -> str:
    lowered = detail.lower()
    if status_code == 404:
        return "profile_not_found"
    if "degree not selected" in lowered:
        return "degree_not_selected"
    if "degree was not found" in lowered or "degree_not_found" in lowered:
        return "degree_not_found"
    if status_code in {401, 503}:
        return "graduation_unavailable"
    return "graduation_unavailable"


async def fetch_graduation_progress_for_user(
    *,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    progress, _error_code = await fetch_graduation_progress_with_meta(
        user_id=user_id,
        settings=settings,
    )
    return progress


async def fetch_graduation_progress_with_meta(
    *,
    user_id: str,
    settings: Settings | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load baseline graduation progress from the API internal route.

    Returns (progress, error_code). error_code is a data-quality warning slug when progress is None.
    """
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url:
        return None, "graduation_unavailable"

    url = f"{base_url}/internal/graduation-progress/users/{user_id}"
    return await _request_graduation_progress_with_meta(
        method="GET",
        url=url,
        settings=cfg,
        json_body=None,
    )


async def preview_graduation_progress_for_user(
    *,
    user_id: str,
    completed_course_numbers: list[str] | None = None,
    additional_course_numbers: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Recompute graduation progress via internal preview route."""
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url:
        return None

    url = f"{base_url}/internal/graduation-progress/preview/users/{user_id}"
    body: dict[str, Any] = {
        "additional_course_numbers": list(additional_course_numbers or []),
    }
    if completed_course_numbers is not None:
        body["completed_course_numbers"] = list(completed_course_numbers)

    progress, _error_code = await _request_graduation_progress_with_meta(
        method="POST",
        url=url,
        settings=cfg,
        json_body=body,
    )
    return progress


async def _request_graduation_progress(
    *,
    method: str,
    url: str,
    settings: Settings,
    json_body: dict[str, Any] | None,
) -> dict[str, Any] | None:
    progress, _error_code = await _request_graduation_progress_with_meta(
        method=method,
        url=url,
        settings=settings,
        json_body=json_body,
    )
    return progress


async def _request_graduation_progress_with_meta(
    *,
    method: str,
    url: str,
    settings: Settings,
    json_body: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    headers: dict[str, str] = {}
    token = settings.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(settings.api_request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "POST":
                response = await client.post(url, headers=headers, json=json_body or {})
            else:
                response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Graduation progress request failed for %s: %s", url, exc)
        return None, "graduation_unavailable"

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = _extract_error_detail(payload if isinstance(payload, dict) else {}, response)
        error_code = graduation_error_code(status_code=response.status_code, detail=detail)
        logger.warning(
            "Graduation progress rejected for %s (status=%s): %s",
            url,
            response.status_code,
            detail,
        )
        return None, error_code

    if not isinstance(payload, dict) or payload.get("success") is not True:
        logger.warning("Graduation progress payload invalid for %s: %s", url, payload)
        return None, "graduation_unavailable"

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Graduation progress missing data envelope for %s", url)
        return None, "graduation_unavailable"

    progress = data.get("graduationProgress")
    if not isinstance(progress, dict):
        logger.warning("Graduation progress missing graduationProgress for %s", url)
        return None, "graduation_unavailable"
    return progress, None
