"""Unit tests for watchdog job handler and enqueue helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.schemas.ai_job import CreateAiJobRequest
from app.services.ai_job_handlers import handle_watchdog_scan
from app.services.watchdog_enqueue import enqueue_watchdog_scan


@pytest.mark.asyncio
async def test_handle_watchdog_scan_delegates_to_service() -> None:
    database = AsyncMock()
    expected = {"status": "ok", "nudgeCount": 1, "nudges": []}

    with (
        patch(
            "app.repositories.user_repository.find_user_by_id",
            new=AsyncMock(return_value={"email": "student@example.com"}),
        ),
        patch(
            "app.services.ai_job_handlers.run_watchdog_for_user",
            new=AsyncMock(return_value=expected),
        ) as run_mock,
    ):
        output = await handle_watchdog_scan(
            database,
            str(ObjectId()),
            {"trigger": "profile_change"},
        )

    assert output == expected
    run_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_watchdog_scan_creates_job() -> None:
    database = AsyncMock()

    with patch(
        "app.services.watchdog_enqueue.create_job_for_user",
        new=AsyncMock(return_value={"status": "queued", "job": {"id": "job1"}}),
    ) as create_mock:
        result = await enqueue_watchdog_scan(
            database,
            str(ObjectId()),
            "new_plan",
            plan_id=str(ObjectId()),
        )

    assert result["status"] == "queued"
    create_mock.assert_awaited_once()
    request = create_mock.await_args.args[2]
    assert isinstance(request, CreateAiJobRequest)
    assert request.type == "watchdog_scan"
    assert request.payload["trigger"] == "new_plan"
