"""HTTP client for internal API academic risk preview."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def fetch_academic_risk_preview(
    *,
    user_id: str,
    course_numbers: list[str],
    semester_code: str,
    max_credits: float | None = None,
    min_credits: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load academic risk preview from the API internal route."""
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url or not course_numbers:
        return None

    url = f"{base_url}/internal/academic-risks/preview/users/{user_id}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = cfg.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    body = {
        "course_numbers": course_numbers,
        "semester_code": semester_code,
        "max_credits": max_credits,
        "min_credits": min_credits,
    }
    timeout = httpx.Timeout(cfg.api_request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        logger.warning("Academic risk preview request failed for %s: %s", url, exc)
        return None

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") or payload.get("detail") or response.text
        logger.warning(
            "Academic risk preview rejected for %s (status=%s): %s",
            url,
            response.status_code,
            detail,
        )
        return None

    if not isinstance(payload, dict) or payload.get("success") is not True:
        logger.warning("Academic risk preview payload invalid for %s: %s", url, payload)
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Academic risk preview missing data envelope for %s", url)
        return None

    analysis = data.get("academicRiskAnalysis")
    if not isinstance(analysis, dict):
        logger.warning("Academic risk preview missing academicRiskAnalysis for %s", url)
        return None
    return analysis
