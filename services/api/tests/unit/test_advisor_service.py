"""Unit tests for the advisor service's call into the internal AI service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.advisor_service import ask_advisor_for_user


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
