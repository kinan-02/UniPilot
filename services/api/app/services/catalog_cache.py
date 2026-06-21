"""Redis cache-aside helpers for read-heavy catalog endpoints."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.db.redis_client import get_redis_client

CATALOG_CACHE_PREFIX = "catalog:"


def _cache_enabled() -> bool:
    settings = get_settings()
    return (
        settings.catalog_cache_enabled
        and settings.environment != "test"
        and bool(settings.redis_url)
    )


def _cache_key(suffix: str) -> str:
    return f"{CATALOG_CACHE_PREFIX}{suffix}"


async def get_cached_json(key_suffix: str) -> Any | None:
    if not _cache_enabled():
        return None

    client = get_redis_client()
    if client is None:
        return None

    try:
        raw = await client.get(_cache_key(key_suffix))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def set_cached_json(key_suffix: str, value: Any) -> None:
    if not _cache_enabled():
        return

    client = get_redis_client()
    if client is None:
        return

    settings = get_settings()
    try:
        await client.setex(
            _cache_key(key_suffix),
            settings.catalog_cache_ttl_seconds,
            json.dumps(value, default=str),
        )
    except Exception:
        return


def offerings_batch_cache_key(
    course_numbers: list[str],
    *,
    academic_year: int | None,
    semester_code: int | None,
) -> str:
    numbers = ",".join(sorted(course_numbers))
    return f"offerings:{numbers}:y{academic_year}:s{semester_code}"


def course_cache_key(course_number: str) -> str:
    return f"course:{course_number}"


def degree_programs_cache_key() -> str:
    return "degree-programs:all"
