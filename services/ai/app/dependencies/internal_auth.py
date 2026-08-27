"""Internal service authentication."""

import logging

from fastapi import Header, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)


async def require_internal_service_token(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
) -> None:
    expected = get_settings().resolved_internal_service_token()
    if not expected:
        # Unauthenticated, and said out loud. `/advise` answers for whatever
        # `user_id` it is handed, so with no token configured anything that can
        # reach this port can read any student's record. That is tolerable while
        # someone runs the service alone and nowhere else, which is why
        # `Settings.validate_production_settings` stops production starting in
        # this state -- but a missing env var is silent by nature, so it is worth
        # a line in the log wherever it happens.
        logger.warning(
            "INTERNAL_SERVICE_TOKEN is not set: /advise is answering unauthenticated "
            "requests for any user_id."
        )
        return

    provided = (x_internal_service_token or "").strip()
    if provided != expected:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized internal service request",
        )
