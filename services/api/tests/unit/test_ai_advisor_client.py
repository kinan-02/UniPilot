"""Unit tests for AI advisor HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.ai_advisor_client import AiAdvisorClientError, ask_advisor
from app.config import Settings


@pytest.mark.asyncio
async def test_ask_advisor_returns_data_on_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success": true, "data": {"response": {"answer": "ok"}}, "error": null}'
    mock_response.json.return_value = {
        "success": True,
        "data": {"response": {"answer": "ok"}},
        "error": None,
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    settings = Settings(
        ai_service_url="http://ai:3001",
        internal_service_token="test-token",
    )

    with patch("app.clients.ai_advisor_client.httpx.AsyncClient", return_value=mock_client):
        result = await ask_advisor(
            question="What is the syllabus?",
            user_id="user-1",
            settings=settings,
        )

    assert result["response"]["answer"] == "ok"
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["headers"]["X-Internal-Service-Token"] == "test-token"
    assert call_kwargs["json"] == {"question": "What is the syllabus?", "user_id": "user-1"}


@pytest.mark.asyncio
async def test_ask_advisor_raises_on_http_error() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.content = b'{"success": false, "error": "OPENAI_API_KEY is not configured"}'
    mock_response.json.return_value = {
        "success": False,
        "error": "OPENAI_API_KEY is not configured",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.ai_advisor_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AiAdvisorClientError) as exc_info:
            await ask_advisor(question="test", user_id="user-1")

    assert exc_info.value.status_code == 503
