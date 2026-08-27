"""Unit tests for the advisor service's call into the internal AI service."""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bson import ObjectId

from app.clients.ai_advisor_client import UNAVAILABLE_DETAIL, AiAdvisorClientError
from app.services.advisor_service import ask_advisor_for_user, stream_advisor_for_user


@pytest.mark.asyncio
async def test_ask_advisor_for_user_sends_the_students_own_user_id() -> None:
    """agent_core fetches everything about the student itself via its own
    tool primitives -- ask_advisor_for_user just forwards the raw question
    and the student's user_id, no pre-built context blob."""
    database = AsyncMock()
    user_id = str(ObjectId())
    ai_response = {
        "question": "מה הסילבוס?",
        "response": {
            "answer": "תשובה",
            "confidence": "high",
            "course_ids": [],
            "wiki_slugs": [],
            "sources": [],
            "contacts": [],
        },
    }

    with patch(
        "app.services.advisor_service.ask_advisor",
        new=AsyncMock(return_value=ai_response),
    ) as ask_mock:
        result = await ask_advisor_for_user(database, user_id, "מה הסילבוס?")

    assert result["status"] == "ok"
    assert ask_mock.await_args.kwargs["user_id"] == user_id
    assert ask_mock.await_args.kwargs["question"] == "מה הסילבוס?"


@pytest.mark.asyncio
async def test_an_unreachable_agent_is_reported_as_unavailable() -> None:
    """The 503 the client raises for an unreachable agent has to land on the
    route's "unavailable" branch rather than its generic error one, because that
    is the branch that tells the student to try again.

    The transport failure itself is converted in `ai_advisor_client`, which owns
    httpx; see `TestTheAgentBeingUnreachable` in `test_ai_advisor_client.py`."""
    database = AsyncMock()
    unreachable = AiAdvisorClientError(status_code=503, detail=UNAVAILABLE_DETAIL)

    with patch(
        "app.services.advisor_service.ask_advisor",
        new=AsyncMock(side_effect=unreachable),
    ):
        result = await ask_advisor_for_user(database, str(ObjectId()), "שאלה")

    assert result["status"] == "unavailable"
    assert result["detail"] == UNAVAILABLE_DETAIL


class TestTheStreamFailingPartWay:
    """`/advise/stream` on the AI side deliberately never raises mid-stream -- it
    emits `{"type": "error"}` instead, so the UI can say something. The proxy in
    front of it has to keep that promise, because by the time the transport fails
    the 200 and the `text/event-stream` headers are already sent and there is no
    status code left to fail with."""

    @staticmethod
    def _failing_stream(error: Exception) -> Any:
        async def _stream(**_kwargs: Any) -> AsyncGenerator[str, None]:
            yield 'data: {"type": "progress", "text": "..."}\n\n'
            raise error

        return _stream

    @pytest.mark.asyncio
    async def test_a_dropped_agent_ends_the_stream_with_an_error_event(self) -> None:
        with patch(
            "app.services.advisor_service.stream_advisor",
            new=self._failing_stream(httpx.ReadTimeout("timed out")),
        ):
            chunks = [
                chunk async for chunk in stream_advisor_for_user(str(ObjectId()), "שאלה")
            ]

        assert any('"type": "error"' in chunk or '"type":"error"' in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_what_was_already_streamed_is_kept(self) -> None:
        """Whatever the agent managed to say before the failure still reaches the
        student; the error event is appended, not substituted."""
        with patch(
            "app.services.advisor_service.stream_advisor",
            new=self._failing_stream(httpx.ConnectError("boom")),
        ):
            chunks = [
                chunk async for chunk in stream_advisor_for_user(str(ObjectId()), "שאלה")
            ]

        assert any('"type": "progress"' in chunk for chunk in chunks)
