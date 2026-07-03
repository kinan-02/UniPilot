"""Tests for semester suggestion HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.semester_suggestion_client import fetch_semester_suggestion_for_user
from app.config import Settings


@pytest.mark.asyncio
async def test_fetch_semester_suggestion_returns_none_without_api_url() -> None:
    settings = Settings(api_service_url="")
    result = await fetch_semester_suggestion_for_user(
        user_id="user-1",
        semester_code="2025-2",
        settings=settings,
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_semester_suggestion_success() -> None:
    settings = Settings(api_service_url="http://api:8000", internal_service_token="secret")
    response = MagicMock()
    response.status_code = 200
    response.content = b'{"success": true}'
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": {
                "status": "ok",
                "plannedCourses": [{"courseNumber": "00140102", "credits": 3}],
                "offeredCourseNumbers": ["00140102", "00940411"],
            },
        }
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.semester_suggestion_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_semester_suggestion_for_user(
            user_id="user-1",
            semester_code="2025-2",
            settings=settings,
        )

    assert result == {
        "status": "ok",
        "plannedCourses": [{"courseNumber": "00140102", "credits": 3}],
        "offeredCourseNumbers": ["00140102", "00940411"],
    }


@pytest.mark.asyncio
async def test_fetch_semester_suggestion_handles_http_error() -> None:
    settings = Settings(api_service_url="http://api:8000")
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.semester_suggestion_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_semester_suggestion_for_user(
            user_id="user-1",
            semester_code="2025-2",
            settings=settings,
        )

    assert result is None
