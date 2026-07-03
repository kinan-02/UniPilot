"""Tests for student user context HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.student_user_context_client import fetch_student_user_context_for_user
from app.config import Settings


@pytest.mark.asyncio
async def test_fetch_student_user_context_returns_none_without_api_url() -> None:
    settings = Settings(api_service_url="")
    result = await fetch_student_user_context_for_user(user_id="user-1", settings=settings)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_student_user_context_success() -> None:
    settings = Settings(api_service_url="http://api:8000", internal_service_token="secret")
    response = MagicMock()
    response.status_code = 200
    response.content = b'{"success": true, "data": {"userContext": {"user_id": "user-1", "completed_courses": ["00940139"]}}}'
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": {"userContext": {"user_id": "user-1", "completed_courses": ["00940139"]}},
        }
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.student_user_context_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_student_user_context_for_user(user_id="user-1", settings=settings)

    assert result == {"user_id": "user-1", "completed_courses": ["00940139"]}


@pytest.mark.asyncio
async def test_fetch_student_user_context_handles_http_error() -> None:
    settings = Settings(api_service_url="http://api:8000")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.student_user_context_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_student_user_context_for_user(user_id="user-1", settings=settings)

    assert result is None
