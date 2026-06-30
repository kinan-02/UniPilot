"""Unit tests for advisor service user-context serialization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.advisor_service import ask_advisor_for_user, build_advisor_user_context


@pytest.mark.asyncio
async def test_build_advisor_user_context_serializes_object_ids() -> None:
    degree_id = ObjectId()
    profile = {
        "degreeId": degree_id,
        "facultyId": "009",
        "catalogYear": 2025,
        "currentSemesterCode": "2025-201",
        "displayName": "Test Student",
        "academicPath": {"trackSlug": "dds"},
    }
    database = AsyncMock()

    with (
        patch(
            "app.services.advisor_service.find_student_profile_by_user_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "app.services.advisor_service.find_all_completed_courses_by_user_id",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.advisor_service.find_courses_by_ids",
            new=AsyncMock(return_value=[]),
        ),
    ):
        context = await build_advisor_user_context(database, str(ObjectId()))

    assert context["degree_id"] == str(degree_id)
    assert isinstance(context["degree_id"], str)


@pytest.mark.asyncio
async def test_ask_advisor_for_user_sends_json_safe_context() -> None:
    degree_id = ObjectId()
    profile = {
        "degreeId": degree_id,
        "facultyId": "009",
        "catalogYear": 2025,
        "currentSemesterCode": "2025-201",
        "academicPath": {"trackSlug": "dds"},
    }
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
            "app.services.advisor_service.find_student_profile_by_user_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "app.services.advisor_service.find_all_completed_courses_by_user_id",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.advisor_service.find_courses_by_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.advisor_service.ask_advisor",
            new=AsyncMock(return_value=ai_response),
        ) as ask_mock,
    ):
        result = await ask_advisor_for_user(database, str(ObjectId()), "מה הסילבוס?")

    assert result["status"] == "ok"
    sent_context = ask_mock.await_args.kwargs["user_context"]
    assert sent_context["degree_id"] == str(degree_id)
