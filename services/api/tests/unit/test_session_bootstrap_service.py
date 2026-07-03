"""Unit tests for session bootstrap service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.session_bootstrap_service import build_session_bootstrap_for_user


@pytest.mark.asyncio
async def test_build_session_bootstrap_includes_graduation_when_ok() -> None:
    database = AsyncMock()
    user_context = {"user_id": "user-1", "completed_courses": ["00940139"]}
    graduation = {"creditsRemaining": 30.0}

    with (
        patch(
            "app.services.session_bootstrap_service.build_student_user_context",
            new=AsyncMock(return_value=user_context),
        ),
        patch(
            "app.services.session_bootstrap_service.get_graduation_progress_for_user",
            new=AsyncMock(return_value={"status": "ok", "progress": graduation}),
        ),
        patch(
            "app.services.session_bootstrap_service.get_curriculum_graph_for_user",
            new=AsyncMock(return_value={"status": "ok", "curriculumGraph": {"nodes": []}}),
        ),
    ):
        payload = await build_session_bootstrap_for_user(database, "user-1")

    assert payload["userContext"] == user_context
    assert payload["graduationProgress"] == graduation
    assert payload["graduationStatus"] == "ok"
    assert payload["graduationError"] is None
    assert payload["curriculumStatus"] == "ok"
    assert payload["curriculumGraph"] == {"nodes": []}
    assert payload["planningContext"]["status"] == "ok"
    assert payload["planningReady"] is True


@pytest.mark.asyncio
async def test_build_session_bootstrap_structures_graduation_failure() -> None:
    database = AsyncMock()
    user_context = {"user_id": "user-1", "completed_courses": []}

    with (
        patch(
            "app.services.session_bootstrap_service.build_student_user_context",
            new=AsyncMock(return_value=user_context),
        ),
        patch(
            "app.services.session_bootstrap_service.get_graduation_progress_for_user",
            new=AsyncMock(return_value={"status": "degree_not_selected"}),
        ),
        patch(
            "app.services.session_bootstrap_service.get_curriculum_graph_for_user",
            new=AsyncMock(return_value={"status": "degree_not_selected"}),
        ),
    ):
        payload = await build_session_bootstrap_for_user(database, "user-1")

    assert payload["userContext"] == user_context
    assert payload["graduationProgress"] is None
    assert payload["graduationStatus"] == "degree_not_selected"
    assert payload["graduationError"] == "degree_not_selected"
    assert payload["curriculumStatus"] == "degree_not_selected"
    assert payload["planningContext"]["status"] == "graduation_unavailable"
    assert payload["planningReady"] is False
