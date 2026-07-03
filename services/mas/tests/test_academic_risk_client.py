"""Unit tests for academic risk preview HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.academic_risk_client import fetch_academic_risk_preview
from app.config import Settings


@pytest.mark.asyncio
async def test_fetch_academic_risk_preview_requires_courses() -> None:
    settings = Settings(api_service_url="http://api:8000")
    result = await fetch_academic_risk_preview(
        user_id="user-1",
        course_numbers=[],
        semester_code="2025-1",
        settings=settings,
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_academic_risk_preview_success() -> None:
    settings = Settings(api_service_url="http://api:8000", internal_service_token="secret")
    response = MagicMock()
    response.content = b'{"success": true, "data": {"academicRiskAnalysis": {"probation": {"pressured": false}}}}'
    response.status_code = 200
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": {"academicRiskAnalysis": {"probation": {"pressured": False}}},
        }
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.academic_risk_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_academic_risk_preview(
            user_id="user-1",
            course_numbers=["00140008"],
            semester_code="2025-1",
            max_credits=22.0,
            min_credits=12.0,
            settings=settings,
        )

    assert result == {"probation": {"pressured": False}}


@pytest.mark.asyncio
async def test_fetch_academic_risk_preview_handles_http_error() -> None:
    settings = Settings(api_service_url="http://api:8000")
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.academic_risk_client.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_academic_risk_preview(
            user_id="user-1",
            course_numbers=["00140008"],
            semester_code="2025-1",
            settings=settings,
        )

    assert result is None
