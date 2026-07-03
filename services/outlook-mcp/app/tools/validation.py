"""Input validation helpers for Outlook MCP tools."""

from __future__ import annotations

import re
from datetime import datetime

from app.config import DEFAULT_MAX_RESULTS, MAX_RESULTS_CAP
from app.graph.errors import OutlookValidationError

ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$"
)
OBJECT_ID_RE = re.compile(r"^[a-fA-F0-9]{24}$")


def validate_user_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if not OBJECT_ID_RE.match(value):
        raise OutlookValidationError("userId must be a valid MongoDB ObjectId")
    return value


def validate_message_id(message_id: str) -> str:
    value = str(message_id or "").strip()
    if not value or len(value) > 512:
        raise OutlookValidationError("messageId is required and must be <= 512 characters")
    return value


def validate_folder_id(folder_id: str | None) -> str | None:
    if folder_id is None:
        return None
    value = str(folder_id).strip()
    if not value or len(value) > 512:
        raise OutlookValidationError("folderId must be <= 512 characters")
    return value


def validate_max_results(max_results: int | None) -> int:
    if max_results is None:
        return DEFAULT_MAX_RESULTS
    if max_results < 1:
        raise OutlookValidationError("maxResults must be >= 1")
    return min(int(max_results), MAX_RESULTS_CAP)


def validate_iso_date(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    if not ISO_DATE_RE.match(stripped):
        raise OutlookValidationError(f"{field_name} must be an ISO-8601 date or datetime")
    try:
        if "T" in stripped:
            datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        else:
            datetime.fromisoformat(stripped)
    except ValueError as exc:
        raise OutlookValidationError(f"{field_name} must be a valid ISO-8601 date") from exc
    return stripped


def validate_body_format(body_format: str | None) -> str:
    normalized = str(body_format or "text").strip().lower()
    if normalized not in {"text", "html"}:
        raise OutlookValidationError('bodyFormat must be "text" or "html"')
    return normalized


def validate_optional_query(value: str | None, *, field_name: str, max_length: int = 500) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    if len(stripped) > max_length:
        raise OutlookValidationError(f"{field_name} must be <= {max_length} characters")
    return stripped
