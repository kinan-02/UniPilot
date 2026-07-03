"""HTTP client for internal API session bootstrap (user context + graduation)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def fetch_session_bootstrap_for_user(
    *,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load combined session bootstrap from the API internal route."""
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url:
        return None

    url = f"{base_url}/internal/session-bootstrap/users/{user_id}"
    headers: dict[str, str] = {}
    token = cfg.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(cfg.api_request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Session bootstrap request failed for %s: %s", url, exc)
        return None

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") or payload.get("detail") or response.text
        logger.warning(
            "Session bootstrap rejected for %s (status=%s): %s",
            url,
            response.status_code,
            detail,
        )
        return None

    if not isinstance(payload, dict) or payload.get("success") is not True:
        logger.warning("Session bootstrap payload invalid for %s: %s", url, payload)
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Session bootstrap missing data envelope for %s", url)
        return None

    user_context = data.get("userContext")
    if not isinstance(user_context, dict):
        logger.warning("Session bootstrap missing userContext for %s", url)
        return None

    return {
        "userContext": user_context,
        "graduationProgress": data.get("graduationProgress"),
        "graduationStatus": data.get("graduationStatus"),
        "graduationError": data.get("graduationError"),
        "curriculumGraph": data.get("curriculumGraph"),
        "curriculumStatus": data.get("curriculumStatus"),
        "curriculumError": data.get("curriculumError"),
        "planningContext": data.get("planningContext"),
        "planningReady": data.get("planningReady"),
    }
