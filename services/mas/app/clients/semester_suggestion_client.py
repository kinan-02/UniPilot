"""HTTP client for internal API semester suggestions (Mongo catalog planner)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def fetch_semester_suggestion_for_user(
    *,
    user_id: str,
    semester_code: str,
    max_credits: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load Progress-aligned semester suggestions from the API internal route."""
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url:
        return None

    url = f"{base_url}/internal/semester-suggestions/users/{user_id}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = cfg.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    body: dict[str, Any] = {"semesterCode": semester_code}
    if max_credits is not None:
        body["maxCredits"] = max_credits

    timeout = httpx.Timeout(cfg.api_request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        logger.warning("Semester suggestion request failed for %s: %s", url, exc)
        return None

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") or payload.get("detail") or response.text
        logger.warning(
            "Semester suggestion rejected for %s (status=%s): %s",
            url,
            response.status_code,
            detail,
        )
        return None

    if not isinstance(payload, dict) or payload.get("success") is not True:
        logger.warning("Semester suggestion payload invalid for %s: %s", url, payload)
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Semester suggestion missing data envelope for %s", url)
        return None

    return data
