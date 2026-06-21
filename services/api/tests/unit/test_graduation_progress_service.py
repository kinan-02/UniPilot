"""Unit tests for graduation_progress_service and planner_enrichment_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId


# ---------------------------------------------------------------------------
# graduation_progress_service
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graduation_progress_returns_profile_not_found():
    from app.services.graduation_progress_service import get_graduation_progress_for_user

    db = MagicMock()
    with patch(
        "app.services.graduation_progress_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await get_graduation_progress_for_user(db, "user1")
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_graduation_progress_returns_degree_not_selected():
    from app.services.graduation_progress_service import get_graduation_progress_for_user

    profile = {"_id": ObjectId(), "degreeId": None}
    db = MagicMock()
    with patch(
        "app.services.graduation_progress_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        result = await get_graduation_progress_for_user(db, "user1")
    assert result["status"] == "degree_not_selected"


@pytest.mark.asyncio
async def test_graduation_progress_returns_degree_not_found():
    from app.services.graduation_progress_service import get_graduation_progress_for_user

    profile = {"_id": ObjectId(), "degreeId": str(ObjectId())}
    db = MagicMock()
    with patch(
        "app.services.graduation_progress_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.graduation_progress_service.catalog_repository.find_degree_program_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await get_graduation_progress_for_user(db, "user1")
    assert result["status"] == "degree_not_found"


@pytest.mark.asyncio
async def test_graduation_progress_returns_ok_with_progress():
    from app.services.graduation_progress_service import get_graduation_progress_for_user

    degree_id = str(ObjectId())
    profile = {"_id": ObjectId(), "degreeId": degree_id}
    degree_program = {
        "_id": ObjectId(),
        "programCode": "009216-1-000",
        "totalCreditsRequired": 180,
        "mandatoryCourseGroups": [],
        "electiveGroups": [],
    }
    db = MagicMock()
    with patch(
        "app.services.graduation_progress_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.graduation_progress_service.catalog_repository.find_degree_program_by_id",
        new_callable=AsyncMock,
        return_value=degree_program,
    ), patch(
        "app.services.graduation_progress_service.catalog_repository.list_hard_requirements_for_program",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.graduation_progress_service.catalog_repository.list_course_pools_for_program",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.graduation_progress_service.find_all_completed_courses_by_user_id",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.graduation_progress_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await get_graduation_progress_for_user(db, "user1")
    assert result["status"] == "ok"
    assert "progress" in result


# ---------------------------------------------------------------------------
# planner_enrichment_service - _stale_course_warnings (sync)
# ---------------------------------------------------------------------------

def test_stale_course_warnings_returns_warning_when_offering_missing():
    from app.services.planner_enrichment_service import _stale_course_warnings

    planned = [{"courseNumber": "00940101", "courseId": "cid1"}]
    result = _stale_course_warnings(planned, offerings_by_number={})
    assert len(result) == 1
    assert result[0]["courseNumber"] == "00940101"
    assert result[0]["status"] == "offering_missing"


def test_stale_course_warnings_no_warning_when_offering_present():
    from app.services.planner_enrichment_service import _stale_course_warnings

    planned = [{"courseNumber": "00940101", "courseId": "cid1"}]
    result = _stale_course_warnings(planned, offerings_by_number={"00940101": {"scheduleGroups": []}})
    assert result == []


def test_stale_course_warnings_skips_courses_without_number():
    from app.services.planner_enrichment_service import _stale_course_warnings

    planned = [{"courseId": "cid1"}]  # no courseNumber
    result = _stale_course_warnings(planned, offerings_by_number={})
    assert result == []


# ---------------------------------------------------------------------------
# planner_enrichment_service - resolve_public_plan_insights (fast paths)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_public_plan_insights_returns_snapshot_when_not_recompute():
    from app.services.planner_enrichment_service import resolve_public_plan_insights

    plan = {
        "_id": ObjectId(),
        "semesters": [],
        "plannerInsights": {"totalCredits": 12},
    }
    db = MagicMock()
    result = await resolve_public_plan_insights(db, "user1", plan, recompute=False, persist_snapshot=False)
    assert result["plannerInsights"]["totalCredits"] == 12


@pytest.mark.asyncio
async def test_resolve_public_plan_insights_enriches_when_no_snapshot():
    from app.services.planner_enrichment_service import resolve_public_plan_insights

    plan = {
        "_id": ObjectId(),
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": []}],
        "version": 1,
    }
    db = MagicMock()
    with patch(
        "app.services.planner_enrichment_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.services.planner_enrichment_service.find_all_completed_courses_by_user_id",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.planner_enrichment_service.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.planner_enrichment_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await resolve_public_plan_insights(
            db, "user1", plan, recompute=False, persist_snapshot=False
        )
    assert "plannerInsights" in result


@pytest.mark.asyncio
async def test_enrich_semester_plan_returns_plan_with_insights():
    from app.services.planner_enrichment_service import enrich_semester_plan

    plan = {
        "_id": ObjectId(),
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": []}],
        "version": 1,
        "explanation": {},
    }
    db = MagicMock()
    with patch(
        "app.services.planner_enrichment_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.services.planner_enrichment_service.find_all_completed_courses_by_user_id",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.planner_enrichment_service.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.planner_enrichment_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await enrich_semester_plan(db, "user1", plan)
    assert "plannerInsights" in result
    insights = result["plannerInsights"]
    assert "totalCredits" in insights
    assert "examSummary" in insights
    assert "staleCourseWarnings" in insights
    assert "lessonSelectionWarnings" in insights
