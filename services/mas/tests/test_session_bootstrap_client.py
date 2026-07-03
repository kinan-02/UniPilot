"""Tests for session bootstrap HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.session_bootstrap_client import fetch_session_bootstrap_for_user
from app.config import Settings


@pytest.mark.asyncio
async def test_fetch_session_bootstrap_returns_none_without_api_url() -> None:
    settings = Settings(api_service_url="")
    result = await fetch_session_bootstrap_for_user(user_id="user-1", settings=settings)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_session_bootstrap_success() -> None:
    settings = Settings(api_service_url="http://api:8000", internal_service_token="secret")
    response = MagicMock()
    response.status_code = 200
    response.content = b'{"success": true}'
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": {
                "userContext": {"user_id": "user-1", "completed_courses": ["00940139"]},
                "graduationProgress": {"creditsRemaining": 12.0},
                "graduationStatus": "ok",
                "graduationError": None,
                "curriculumGraph": {"nodes": []},
                "curriculumStatus": "ok",
                "curriculumError": None,
                "planningContext": {"status": "ok", "transcriptCourseNumbers": ["00940139"]},
                "planningReady": True,
            },
        }
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.session_bootstrap_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_session_bootstrap_for_user(user_id="user-1", settings=settings)

    assert result == {
        "userContext": {"user_id": "user-1", "completed_courses": ["00940139"]},
        "graduationProgress": {"creditsRemaining": 12.0},
        "graduationStatus": "ok",
        "graduationError": None,
        "curriculumGraph": {"nodes": []},
        "curriculumStatus": "ok",
        "curriculumError": None,
        "planningContext": {"status": "ok", "transcriptCourseNumbers": ["00940139"]},
        "planningReady": True,
    }


@pytest.mark.asyncio
async def test_fetch_session_bootstrap_handles_http_error() -> None:
    settings = Settings(api_service_url="http://api:8000")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.session_bootstrap_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_session_bootstrap_for_user(user_id="user-1", settings=settings)

    assert result is None
