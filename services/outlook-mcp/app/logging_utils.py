"""Safe audit logging — never log tokens or email bodies."""

from __future__ import annotations

import logging
import re
from typing import Any

SENSITIVE_PATTERNS = (
    re.compile(r"access[_-]?token", re.IGNORECASE),
    re.compile(r"refresh[_-]?token", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"contentBytes", re.IGNORECASE),
    re.compile(r"bodyPreview", re.IGNORECASE),
    re.compile(r'"body"', re.IGNORECASE),
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def sanitize_log_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        if any(pattern.search(str(key)) for pattern in SENSITIVE_PATTERNS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 120:
            sanitized[key] = f"{value[:40]}…[truncated]"
        else:
            sanitized[key] = value
    return sanitized


def log_tool_call(logger: logging.Logger, *, tool_name: str, user_id: str, extra: dict[str, Any] | None = None) -> None:
    payload = {"tool": tool_name, "userId": user_id}
    if extra:
        payload.update(sanitize_log_fields(extra))
    logger.info("outlook_mcp_tool_call", extra={"audit": payload})
