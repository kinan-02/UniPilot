"""Unit tests for graduation progress HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.graduation_progress_client import (
    GraduationProgressClientError,
    fetch_graduation_progress_for_user,
    preview_graduation_progress_for_user,
)
from app.config import Settings


def test_graduation_progress_client_error_fields() -> None:
    error = GraduationProgressClientError(status_code=503, detail="unavailable")
    assert error.status_code == 503
    assert error.detail == "unavailable"
    assert str(error) == "unavailable"


@pytest.mark.asyncio
async def test_fetch_graduation_progress_returns_none_without_api_url() -> None:
    settings = Settings(api_service_url="")
    result = await fetch_graduation_progress_for_user(user_id="user-1", settings=settings)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_graduation_progress_with_meta_maps_degree_not_selected() -> None:
    settings = Settings(
        api_service_url="http://api:8000",
        internal_service_token="token",
    )
    response = MagicMock()
    response.status_code = 400
    response.content = b'{"detail":"Degree not selected on student profile"}'
    response.json.return_value = {"detail": "Degree not selected on student profile"}
    response.text = response.content.decode()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.graduation_progress_client.httpx.AsyncClient", return_value=mock_client):
        from app.clients.graduation_progress_client import fetch_graduation_progress_with_meta

        progress, error_code = await fetch_graduation_progress_with_meta(user_id="user-1", settings=settings)

    assert progress is None
    assert error_code == "degree_not_selected"



@pytest.mark.asyncio
async def test_fetch_graduation_progress_success() -> None:
    settings = Settings(api_service_url="http://api:8000", internal_service_token="secret")
    response = MagicMock()
    response.content = b'{"success": true, "data": {"graduationProgress": {"completedCredits": 40}}}'
    response.status_code = 200
    response.json = MagicMock(return_value={"success": True, "data": {"graduationProgress": {"completedCredits": 40}}})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.graduation_progress_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_graduation_progress_for_user(user_id="user-1", settings=settings)

    assert result == {"completedCredits": 40}
    headers = mock_client.get.await_args.kwargs["headers"]
    assert headers["X-Internal-Service-Token"] == "secret"


@pytest.mark.asyncio
async def test_preview_graduation_progress_handles_http_error() -> None:
    settings = Settings(api_service_url="http://api:8000")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.graduation_progress_client.httpx.AsyncClient", return_value=mock_client):
        result = await preview_graduation_progress_for_user(
            user_id="user-1",
            additional_course_numbers=["00140008"],
            settings=settings,
        )

    assert result is None


@pytest.mark.asyncio
async def test_preview_graduation_progress_rejects_bad_payload() -> None:
    settings = Settings(api_service_url="http://api:8000")
    response = MagicMock()
    response.content = b'{"success": false}'
    response.status_code = 200
    response.json = MagicMock(return_value={"success": False})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.graduation_progress_client.httpx.AsyncClient", return_value=mock_client):
        result = await preview_graduation_progress_for_user(
            user_id="user-1",
            completed_course_numbers=["00140008"],
            additional_course_numbers=["00940139"],
            settings=settings,
        )

    assert result is None
