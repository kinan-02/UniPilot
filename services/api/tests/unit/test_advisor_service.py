"""Unit tests for advisor service user-context serialization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.advisor_service import ask_advisor_for_user, build_advisor_user_context


@pytest.mark.asyncio
async def test_build_advisor_user_context_strips_user_id() -> None:
    database = AsyncMock()
    with patch(
        "app.services.advisor_service.build_student_user_context",
        new=AsyncMock(
            return_value={
                "user_id": "user-1",
                "completed_courses": ["00940139"],
                "degree_id": "degree-1",
            }
        ),
    ):
        context = await build_advisor_user_context(database, "user-1")

    assert "user_id" not in context
    assert context["completed_courses"] == ["00940139"]


@pytest.mark.asyncio
async def test_ask_advisor_for_user_sends_json_safe_context() -> None:
    database = AsyncMock()
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

    with (
        patch(
            "app.services.advisor_service.build_advisor_user_context",
            new=AsyncMock(return_value={"degree_id": "degree-1", "completed_courses": []}),
        ),
        patch(
            "app.services.advisor_service.ask_advisor",
            new=AsyncMock(return_value=ai_response),
        ) as ask_mock,
    ):
        result = await ask_advisor_for_user(database, str(ObjectId()), "מה הסילבוס?")

    assert result["status"] == "ok"
    sent_context = ask_mock.await_args.kwargs["user_context"]
    assert sent_context["degree_id"] == "degree-1"
