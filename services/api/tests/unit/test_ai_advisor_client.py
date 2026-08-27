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


class TestTheAgentBeingUnreachable:
    """The agent being down, or slower than `ai_advisor_timeout_seconds`, is an
    ordinary production event. httpx spells those as exceptions, and an exception
    escaping this client becomes a 500 -- so they are converted here, at the only
    layer that knows about httpx at all."""

    @staticmethod
    def _client_raising(error: Exception) -> AsyncMock:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=error)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    @pytest.mark.parametrize(
        "transport_error",
        [
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("timed out"),
            httpx.RemoteProtocolError("peer closed connection"),
        ],
        ids=["service_down", "agent_too_slow", "connection_dropped"],
    )
    @pytest.mark.asyncio
    async def test_a_transport_failure_becomes_a_503(self, transport_error: Exception) -> None:
        settings = Settings(ai_service_url="http://ai:3001", internal_service_token="t")

        with patch(
            "app.clients.ai_advisor_client.httpx.AsyncClient",
            return_value=self._client_raising(transport_error),
        ):
            with pytest.raises(AiAdvisorClientError) as caught:
                await ask_advisor(question="q", user_id="u", settings=settings)

        assert caught.value.status_code == 503

    @pytest.mark.asyncio
    async def test_the_students_message_does_not_name_the_internal_host(self) -> None:
        """`[Errno 111] Connect call failed ('10.0.3.7', 3001)` is what httpx says.
        It goes to the log; the student gets fixed text."""
        settings = Settings(ai_service_url="http://ai:3001", internal_service_token="t")
        leaky = httpx.ConnectError("[Errno 111] Connect call failed ('10.0.3.7', 3001)")

        with patch(
            "app.clients.ai_advisor_client.httpx.AsyncClient",
            return_value=self._client_raising(leaky),
        ):
            with pytest.raises(AiAdvisorClientError) as caught:
                await ask_advisor(question="q", user_id="u", settings=settings)

        assert "10.0.3.7" not in caught.value.detail
        assert "3001" not in caught.value.detail

    @pytest.mark.asyncio
    async def test_a_gateway_answering_with_html_is_a_502_not_a_crash(self) -> None:
        """A proxy in front of the agent returns an HTML error page. Calling
        `.json()` on that raises, and an unparsed body is not a reason to 500."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.content = b"<html><body>Bad Gateway</body></html>"
        mock_response.json.side_effect = ValueError("Expecting value")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        settings = Settings(ai_service_url="http://ai:3001", internal_service_token="t")

        with patch("app.clients.ai_advisor_client.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AiAdvisorClientError) as caught:
                await ask_advisor(question="q", user_id="u", settings=settings)

        assert caught.value.status_code == 502
