"""HTTP client for internal API student user context."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def fetch_student_user_context_for_user(
    *,
    user_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load canonical student context from the API internal route."""
    cfg = settings or get_settings()
    base_url = cfg.resolved_api_service_url()
    if not base_url:
        return None

    url = f"{base_url}/internal/user-context/users/{user_id}"
    headers: dict[str, str] = {}
    token = cfg.resolved_internal_service_token()
    if token:
        headers["X-Internal-Service-Token"] = token

    timeout = httpx.Timeout(cfg.api_request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Student user context request failed for %s: %s", url, exc)
        return None

    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = payload.get("error") or payload.get("detail") or response.text
        logger.warning(
            "Student user context rejected for %s (status=%s): %s",
            url,
            response.status_code,
            detail,
        )
        return None

    if not isinstance(payload, dict) or payload.get("success") is not True:
        logger.warning("Student user context payload invalid for %s: %s", url, payload)
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("Student user context missing data envelope for %s", url)
        return None

    user_context = data.get("userContext")
    return user_context if isinstance(user_context, dict) else None
