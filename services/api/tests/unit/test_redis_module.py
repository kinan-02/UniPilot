"""Unit tests for app/db/redis.py — targets the close_redis delegate (line 13)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import app.db.redis as redis_module


@pytest.mark.asyncio
async def test_close_redis_delegates_to_close_redis_client() -> None:
    """close_redis must forward the call to close_redis_client."""
    with patch(
        "app.db.redis.close_redis_client", new_callable=AsyncMock
    ) as mock_close:
        await redis_module.close_redis()
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_connectivity_delegates_to_pool_check() -> None:
    """check_redis_connectivity wraps _check_pool_connectivity."""
    with patch(
        "app.db.redis._check_pool_connectivity",
        new_callable=AsyncMock,
        return_value="connected",
    ) as mock_check:
        result = await redis_module.check_redis_connectivity()
    assert result == "connected"
    mock_check.assert_awaited_once()
