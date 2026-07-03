"""Redis cache for planner graph tool results within a MAS session."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db.redis_client import get_redis_client

TOOL_CACHE_TTL_SECONDS = 86_400
CACHEABLE_TOOLS = frozenset(
    {
        "retrieve_graph_data",
        "list_wiki_catalog",
        "list_semester_catalogs",
        "select_semester_catalog",
    }
)


def _args_digest(args: dict[str, Any]) -> str:
    normalized = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def tool_cache_key(*, session_id: str, tool_name: str, args: dict[str, Any]) -> str:
    return f"mas:session:{session_id}:tool:{tool_name}:{_args_digest(args)}"


async def get_cached_tool_result(
    *,
    session_id: str | None,
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    if not session_id or tool_name not in CACHEABLE_TOOLS:
        return None

    client = get_redis_client()
    if client is None:
        return None

    key = tool_cache_key(session_id=session_id, tool_name=tool_name, args=args)
    try:
        return await client.get(key)
    except Exception:  # noqa: BLE001
        return None


async def set_cached_tool_result(
    *,
    session_id: str | None,
    tool_name: str,
    args: dict[str, Any],
    result: str,
) -> None:
    if not session_id or tool_name not in CACHEABLE_TOOLS:
        return

    client = get_redis_client()
    if client is None:
        return

    key = tool_cache_key(session_id=session_id, tool_name=tool_name, args=args)
    try:
        await client.set(key, result, ex=TOOL_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        return
