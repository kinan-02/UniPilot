"""Tests for enriched MAS user context loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.user_context_loader import load_enriched_user_context


@pytest.mark.asyncio
async def test_load_enriched_user_context_prefers_api_bootstrap() -> None:
    database = AsyncMock()
    base_context = {"user_id": "user-1", "completed_courses": ["00940139"]}
    graduation = {"creditsRemaining": 40.0, "remainingMandatoryCourses": []}
    bootstrap = {
        "userContext": base_context,
        "graduationProgress": graduation,
        "graduationStatus": "ok",
        "graduationError": None,
        "planningContext": {
            "status": "ok",
            "transcriptCourseNumbers": ["00940139", "00140008"],
            "pathPriorityCourseNumbers": ["00140102"],
        },
        "planningReady": True,
        "curriculumGraph": {"nodes": []},
        "curriculumStatus": "ok",
        "curriculumError": None,
    }

    with (
        patch(
            "app.services.user_context_loader.fetch_session_bootstrap_for_user",
            new=AsyncMock(return_value=bootstrap),
        ),
        patch(
            "app.services.user_context_loader.fetch_student_user_context_for_user",
            new=AsyncMock(),
        ) as split_fetch,
        patch(
            "app.services.user_context_loader.enrich_user_context_with_graduation_path",
            side_effect=lambda ctx: {**ctx, "path_priority_courses": ["00140008"]},
        ),
    ):
        context = await load_enriched_user_context(database, "user-1")

    split_fetch.assert_not_called()
    assert context["context_source"] == "api_bootstrap"
    assert context["graduation_progress"] == graduation
    assert context["completed_courses"] == ["00940139", "00140008"]
    assert context["path_priority_courses"] == ["00140102"]
    assert context["planning_source"] == "progress_bundle"
    assert context["planning_ready"] is True
    assert context["curriculum_graph"] == {"nodes": []}


@pytest.mark.asyncio
async def test_load_enriched_user_context_attaches_api_semester_catalog() -> None:
    database = AsyncMock()
    base_context = {
        "user_id": "user-1",
        "plan_semester_code": "2025-2",
        "completed_courses": ["00940139"],
        "preferences": {"maxCreditsPerSemester": 18},
    }
    graduation = {"creditsRemaining": 40.0, "remainingMandatoryCourses": []}
    bootstrap = {
        "userContext": base_context,
        "graduationProgress": graduation,
        "graduationStatus": "ok",
        "graduationError": None,
        "planningContext": {
            "status": "ok",
            "transcriptCourseNumbers": ["00940139"],
            "pathPriorityCourseNumbers": ["00140102"],
        },
        "planningReady": True,
    }
    api_catalog = {
        "status": "ok",
        "plannedCourses": [{"courseNumber": "00140102", "credits": 3}],
        "offeredCourseNumbers": ["00140102", "00940411"],
    }

    with (
        patch(
            "app.services.user_context_loader.fetch_session_bootstrap_for_user",
            new=AsyncMock(return_value=bootstrap),
        ),
        patch(
            "app.services.user_context_loader.fetch_semester_suggestion_for_user",
            new=AsyncMock(return_value=api_catalog),
        ),
        patch(
            "app.services.user_context_loader.enrich_user_context_with_graduation_path",
            side_effect=lambda ctx: ctx,
        ),
    ):
        context = await load_enriched_user_context(database, "user-1")

    assert context["catalog_source"] == "api_mongo"
    assert context["api_suggested_course_numbers"] == ["00140102"]
    assert context["api_course_credits"] == {"00140102": 3.0}
    assert context["api_semester_catalog"] == api_catalog


@pytest.mark.asyncio
async def test_load_enriched_user_context_merges_graduation_progress_via_split() -> None:
    database = AsyncMock()
    base_context = {"user_id": "user-1", "completed_courses": ["00940139"]}
    graduation = {"creditsRemaining": 40.0, "remainingMandatoryCourses": []}

    with (
        patch(
            "app.services.user_context_loader.fetch_session_bootstrap_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.user_context_loader.fetch_student_user_context_for_user",
            new=AsyncMock(return_value=base_context),
        ),
        patch(
            "app.services.user_context_loader.get_effector_gateway",
        ) as gateway_factory,
        patch(
            "app.services.user_context_loader.enrich_user_context_with_graduation_path",
            side_effect=lambda ctx: {**ctx, "path_priority_courses": ["00140008"]},
        ),
    ):
        gateway = AsyncMock()
        gateway.fetch_graduation_progress_with_meta = AsyncMock(return_value=(graduation, None))
        gateway_factory.return_value = gateway

        context = await load_enriched_user_context(database, "user-1")

    assert context["context_source"] == "api_split"
    assert context["graduation_progress"] == graduation
    assert context["path_priority_courses"] == ["00140008"]


@pytest.mark.asyncio
async def test_load_enriched_user_context_falls_back_to_mongo() -> None:
    database = AsyncMock()
    mongo_context = {"user_id": "user-1", "completed_courses": []}

    with (
        patch(
            "app.services.user_context_loader.fetch_session_bootstrap_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.user_context_loader.fetch_student_user_context_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.user_context_loader.build_user_context",
            new=AsyncMock(return_value=mongo_context),
        ),
        patch("app.services.user_context_loader.get_effector_gateway") as gateway_factory,
    ):
        gateway = AsyncMock()
        gateway.fetch_graduation_progress_with_meta = AsyncMock(return_value=(None, "graduation_unavailable"))
        gateway_factory.return_value = gateway

        context = await load_enriched_user_context(database, "user-1")

    assert context["context_source"] == "mongo_fallback"
    assert context["completed_courses"] == []
    assert "graduation_unavailable" in context["data_quality"]["warnings"]


@pytest.mark.asyncio
async def test_load_enriched_user_context_records_graduation_warning_from_bootstrap() -> None:
    database = AsyncMock()
    bootstrap = {
        "userContext": {"user_id": "user-1"},
        "graduationProgress": None,
        "graduationStatus": "degree_not_selected",
        "graduationError": "degree_not_selected",
        "planningContext": {"status": "graduation_unavailable"},
        "planningReady": False,
    }

    with patch(
        "app.services.user_context_loader.fetch_session_bootstrap_for_user",
        new=AsyncMock(return_value=bootstrap),
    ):
        context = await load_enriched_user_context(database, "user-1")

    assert context["context_source"] == "api_bootstrap"
    assert context["data_quality"]["warnings"] == ["degree_not_selected"]
    assert context["planning_ready"] is False


@pytest.mark.asyncio
async def test_load_enriched_user_context_records_graduation_warning_via_split() -> None:
    database = AsyncMock()

    with (
        patch(
            "app.services.user_context_loader.fetch_session_bootstrap_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.user_context_loader.fetch_student_user_context_for_user",
            new=AsyncMock(return_value={"user_id": "user-1"}),
        ),
        patch("app.services.user_context_loader.get_effector_gateway") as gateway_factory,
    ):
        gateway = AsyncMock()
        gateway.fetch_graduation_progress_with_meta = AsyncMock(
            return_value=(None, "degree_not_selected")
        )
        gateway_factory.return_value = gateway

        context = await load_enriched_user_context(database, "user-1")

    assert context["data_quality"]["warnings"] == ["degree_not_selected"]
