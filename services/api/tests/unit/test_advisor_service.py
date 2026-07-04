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
        patch(
            "app.services.advisor_service.build_planning_context_envelope",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "available": True,
                    "graduation": {"completedCredits": 10},
                }
            ),
        ),
    ):
        context = await build_advisor_user_context(database, str(ObjectId()))

    assert context["degree_id"] == str(degree_id)
    assert isinstance(context["degree_id"], str)
    assert context["transcript"] == []
    assert context["planning_context"]["available"] is True


@pytest.mark.asyncio
async def test_ask_advisor_for_user_omits_agent_trace_by_default() -> None:
    ai_response = {
        "question": "מה הסילבוס?",
        "retrieval_agent": {"status": "ok", "iterations": 2, "steps": [{"iteration": 1}]},
        "profile_agent_invocations": [{"sub_question": "eligibility"}],
        "retrieval_blocks": [{"intent": "syllabus"}],
        "response": {"answer": "תשובה", "confidence": "high"},
    }
    database = AsyncMock()

    with (
        patch(
            "app.services.advisor_service.build_advisor_user_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.advisor_service.ask_advisor",
            new=AsyncMock(return_value=ai_response),
        ),
        patch(
            "app.services.advisor_service.persist_advisor_exchange",
            new=AsyncMock(return_value={"status": "ok"}),
        ),
    ):
        result = await ask_advisor_for_user(database, str(ObjectId()), "מה הסילבוס?")

    assert result["status"] == "ok"
    assert "agentTrace" not in result["advisor"]


@pytest.mark.asyncio
async def test_ask_advisor_for_user_includes_agent_trace_when_requested() -> None:
    ai_response = {
        "question": "האם אני זכאי?",
        "retrieval_agent": {"status": "ok", "iterations": 1, "steps": [{"iteration": 1}]},
        "profile_agent_invocations": [{"sub_question": "eligibility", "status": "ok"}],
        "retrieval_blocks": [{"intent": "course_fit", "source": "profile_agent"}],
        "semester_resolution": {"confidence": "high"},
        "response": {"answer": "כן", "confidence": "medium"},
    }
    database = AsyncMock()

    with (
        patch(
            "app.services.advisor_service.build_advisor_user_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.advisor_service.ask_advisor",
            new=AsyncMock(return_value=ai_response),
        ),
        patch(
            "app.services.advisor_service.persist_advisor_exchange",
            new=AsyncMock(return_value={"status": "ok"}),
        ),
    ):
        result = await ask_advisor_for_user(
            database,
            str(ObjectId()),
            "האם אני זכאי?",
            include_agent_trace=True,
        )

    trace = result["advisor"]["agentTrace"]
    assert trace["retrievalAgent"]["status"] == "ok"
    assert len(trace["profileAgentInvocations"]) == 1
    assert len(trace["retrievalBlocks"]) == 1


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
            "app.services.advisor_service.build_planning_context_envelope",
            new=AsyncMock(return_value={"status": "ok", "available": True, "graduation": {}}),
        ),
        patch(
            "app.services.advisor_service.ask_advisor",
            new=AsyncMock(return_value=ai_response),
        ) as ask_mock,
        patch(
            "app.services.advisor_service.persist_advisor_exchange",
            new=AsyncMock(return_value={"status": "ok"}),
        ),
    ):
        result = await ask_advisor_for_user(database, str(ObjectId()), "מה הסילבוס?")

    assert result["status"] == "ok"
    sent_context = ask_mock.await_args.kwargs["user_context"]
    assert sent_context["degree_id"] == str(degree_id)
