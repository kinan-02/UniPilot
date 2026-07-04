"""Internal service authentication (worker → API)."""

from fastapi import Header, HTTPException

from app.config import get_settings


async def require_internal_service_token(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
) -> None:
    expected = get_settings().resolved_internal_service_token()
    if not expected:
        return

    provided = (x_internal_service_token or "").strip()
    if provided != expected:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized internal service request",
        )
