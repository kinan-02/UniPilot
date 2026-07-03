"""Unit tests for planner tool result cache."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.tool_result_cache import (
    get_cached_tool_result,
    set_cached_tool_result,
    tool_cache_key,
)


def test_tool_cache_key_is_stable() -> None:
    key_a = tool_cache_key(session_id="s1", tool_name="retrieve_graph_data", args={"intent": "schedule"})
    key_b = tool_cache_key(session_id="s1", tool_name="retrieve_graph_data", args={"intent": "schedule"})
    assert key_a == key_b


@pytest.mark.asyncio
async def test_set_and_get_cached_tool_result() -> None:
    mock_client = AsyncMock()
    stored: dict[str, str] = {}

    async def _set(key, value, ex=None):
        stored[key] = value

    async def _get(key):
        return stored.get(key)

    mock_client.set = AsyncMock(side_effect=_set)
    mock_client.get = AsyncMock(side_effect=_get)

    with patch("app.services.tool_result_cache.get_redis_client", return_value=mock_client):
        await set_cached_tool_result(
            session_id="abc",
            tool_name="retrieve_graph_data",
            args={"intent": "eligibility", "course_id": "00940139"},
            result='{"ok": true}',
        )
        cached = await get_cached_tool_result(
            session_id="abc",
            tool_name="retrieve_graph_data",
            args={"intent": "eligibility", "course_id": "00940139"},
        )

    assert cached == '{"ok": true}'
