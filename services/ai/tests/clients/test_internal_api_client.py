"""The agent's one HTTP call back into `api`, and what it does when that fails.

`dispatch` already turns an `InternalApiClientError` into a DEFECT, which is the
whole point of the grounded-facts design: the model SEES that the plan could not
be built and can answer around it -- say so, or answer the part that did not need
a plan. An exception that is not that type skips the handler and takes the whole
run down instead, and the student gets nothing rather than less.

So the job here is narrow: every way the api can fail to answer has to leave this
module as `InternalApiClientError`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.internal_api_client import InternalApiClientError, fetch_term_plan
from app.config import Settings

_ASYNC_CLIENT = "app.clients.internal_api_client.httpx.AsyncClient"


def _settings() -> Settings:
    return Settings(api_service_url="http://api:3000", internal_service_token="t")


def _client_returning(response: Any) -> AsyncMock:
    client = AsyncMock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _client_raising(error: Exception) -> AsyncMock:
    client = AsyncMock()
    client.request = AsyncMock(side_effect=error)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def _plan() -> dict[str, Any]:
    return await fetch_term_plan(
        user_id="student-1",
        semester_codes=["2025-1"],
        candidates=[{"courseNumber": "00940412"}],
        settings=_settings(),
    )


class TestTheApiNotAnswering:
    @pytest.mark.parametrize(
        "transport_error",
        [
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("timed out"),
            httpx.RemoteProtocolError("peer closed connection"),
        ],
        ids=["api_down", "planner_too_slow", "connection_dropped"],
    )
    async def test_a_transport_failure_is_still_an_InternalApiClientError(
        self, transport_error: Exception
    ) -> None:
        with patch(_ASYNC_CLIENT, return_value=_client_raising(transport_error)):
            with pytest.raises(InternalApiClientError):
                await _plan()

    async def test_the_detail_does_not_name_the_internal_host(self) -> None:
        """This detail is written into a DEFECT, and a defect's message is shown
        to the model -- which may quote it. `('10.0.3.7', 3000)` is not something
        to put in front of a student."""
        leaky = httpx.ConnectError("[Errno 111] Connect call failed ('10.0.3.7', 3000)")

        with patch(_ASYNC_CLIENT, return_value=_client_raising(leaky)):
            with pytest.raises(InternalApiClientError) as caught:
                await _plan()

        assert "10.0.3.7" not in caught.value.detail
        assert "3000" not in caught.value.detail

    async def test_a_gateway_answering_with_html_is_not_a_json_crash(self) -> None:
        response = MagicMock()
        response.status_code = 502
        response.content = b"<html><body>Bad Gateway</body></html>"
        response.json.side_effect = ValueError("Expecting value")

        with patch(_ASYNC_CLIENT, return_value=_client_returning(response)):
            with pytest.raises(InternalApiClientError) as caught:
                await _plan()

        assert caught.value.status_code == 502


class TestTheApiAnsweringProperly:
    async def test_a_refusal_keeps_its_detail(self) -> None:
        """A 400 from the planner says something useful -- which semesterCode was
        wrong. That has to survive into the defect the model reads."""
        response = MagicMock()
        response.status_code = 400
        response.content = b'{"detail": "Invalid semesterCode: 2025-9"}'
        response.json.return_value = {"detail": "Invalid semesterCode: 2025-9"}

        with patch(_ASYNC_CLIENT, return_value=_client_returning(response)):
            with pytest.raises(InternalApiClientError) as caught:
                await _plan()

        assert "Invalid semesterCode: 2025-9" in caught.value.detail

    async def test_a_good_plan_comes_back_unwrapped(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"success": true, "data": {"terms": []}}'
        response.json.return_value = {"success": True, "data": {"terms": [], "unscheduled": []}}

        with patch(_ASYNC_CLIENT, return_value=_client_returning(response)):
            result = await _plan()

        assert result == {"terms": [], "unscheduled": []}
