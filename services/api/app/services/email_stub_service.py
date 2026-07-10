"""Log-only email stub for watchdog nudges (AGT-8)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def send_watchdog_email_stub(
    *,
    user_id: str,
    email: str | None,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an email that would be sent in production; no SMTP in MVP."""
    logger.info(
        "watchdog_email_stub user_id=%s email=%s title=%s body=%s metadata=%s",
        user_id,
        email or "unknown",
        title,
        body,
        metadata or {},
    )
