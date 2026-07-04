"""Unit tests for AI job service and handlers."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch

import pytest
from bson import ObjectId

from app.schemas.ai_job import CreateAiJobRequest
from app.services.ai_job_handlers import handle_advisor_deep_plan
from app.services.ai_job_service import create_job_for_user, process_job_by_id


@pytest.mark.asyncio
async def test_create_job_enqueues_and_returns_pending() -> None:
    database = AsyncMock()
    created_id = ObjectId()

    with (
        patch(
            "app.services.ai_job_service.create_ai_job",
            new=AsyncMock(
                return_value={
                    "_id": created_id,
                    "type": "advisor_deep_plan",
                    "status": "pending",
                    "payload": {"question": "test"},
                    "result": None,
                    "error": None,
                    "createdAt": None,
                    "updatedAt": None,
                    "startedAt": None,
                    "finishedAt": None,
                }
            ),
        ),
        patch(
            "app.services.ai_job_service.enqueue_ai_job",
            new=AsyncMock(),
        ) as enqueue_mock,
    ):
        result = await create_job_for_user(
            database,
            str(ObjectId()),
            CreateAiJobRequest(
                type="advisor_deep_plan",
                payload={"question": "Am I eligible for 00440148?"},
            ),
        )

    assert result["status"] == "queued"
    assert result["job"]["status"] == "pending"
    enqueue_mock.assert_awaited_once_with(str(created_id), settings=ANY)


@pytest.mark.asyncio
async def test_handle_advisor_deep_plan_maps_success() -> None:
    database = AsyncMock()
    advisor_result = {
        "status": "ok",
        "advisor": {"answer": "Yes", "confidence": "high"},
        "conversation": {"id": str(ObjectId())},
    }

    with patch(
        "app.services.ai_job_handlers.ask_advisor_for_user",
        new=AsyncMock(return_value=advisor_result),
    ):
        output = await handle_advisor_deep_plan(
            database,
            str(ObjectId()),
            {"question": "Am I eligible?"},
        )

    assert output["advisor"]["answer"] == "Yes"
    assert "conversation" in output


@pytest.mark.asyncio
async def test_process_job_marks_failed_on_handler_error() -> None:
    database = AsyncMock()
    job_id = str(ObjectId())

    with (
        patch(
            "app.services.ai_job_service.mark_ai_job_processing",
            new=AsyncMock(
                return_value={
                    "_id": ObjectId(job_id),
                    "userId": ObjectId(),
                    "type": "advisor_deep_plan",
                    "payload": {"question": "fail"},
                }
            ),
        ),
        patch(
            "app.services.ai_job_service.dispatch_ai_job_handler",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "app.services.ai_job_service.mark_ai_job_failed",
            new=AsyncMock(return_value={}),
        ) as failed_mock,
    ):
        result = await process_job_by_id(database, job_id)

    assert result["status"] == "failed"
    failed_mock.assert_awaited_once()
