"""Internal service-to-service authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings


async def require_internal_service_token(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
) -> None:
    expected = get_settings().resolved_internal_service_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Internal service token is not configured")

    provided = (x_internal_service_token or "").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized internal service request")
