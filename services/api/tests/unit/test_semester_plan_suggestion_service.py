"""Unit tests for semester plan suggestion service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.semester_plan_suggestion_service import (
    suggest_semester_courses,
    suggest_semester_schedule,
)


@pytest.mark.asyncio
async def test_suggest_semester_courses_propagates_planning_context_error():
    database = AsyncMock()
    with patch(
        "app.services.semester_plan_suggestion_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "profile_not_found"},
    ):
        result = await suggest_semester_courses(database, "user-1", semester_code="2025-2")

    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_suggest_semester_courses_rejects_invalid_semester_code():
    database = AsyncMock()
    with patch(
        "app.services.semester_plan_suggestion_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "ok", "profile": {}, "degree": {}, "catalogCourses": []},
    ):
        result = await suggest_semester_courses(database, "user-1", semester_code="2025-9")

    assert result["status"] == "validation_error"
    assert "Invalid semesterCode" in result["errors"][0]


@pytest.mark.asyncio
async def test_suggest_semester_courses_sets_partial_and_empty_flags():
    database = AsyncMock()
    context = {
        "status": "ok",
        "profile": {"preferences": {"maxCreditsPerSemester": 18}},
        "degree": {"programCode": "009216-1-000"},
        "catalogCourses": [
            {
                "_id": "course-a",
                "courseNumber": "10001",
                "title": "Course A",
                "credits": 3,
                "prerequisites": [],
            }
        ],
        "graduationProgress": {"buckets": []},
        "hardRequirements": [],
        "poolDocuments": [],
        "semesterMatrixDocuments": [],
        "completedCourseRecords": [],
    }
    selection = {
        "selectedCourses": [{"courseId": "course-a", "courseNumber": "10001", "credits": 3}],
        "totalCredits": 3,
        "skippedDueToWorkload": [],
        "skippedDueToConflicts": [],
        "skippedDueToUnavailable": [],
        "activeMatrixSemester": None,
    }

    with (
        patch(
            "app.services.semester_plan_suggestion_service.load_planning_context",
            new_callable=AsyncMock,
            return_value=context,
        ),
        patch(
            "app.services.semester_plan_suggestion_service.build_candidate_pools",
            return_value={
                "mandatoryCandidates": [{"_id": "course-a", "number": "10001", "title": "A", "credits": 3}],
                "electiveCandidates": [],
                "coursesById": {"course-a": context["catalogCourses"][0]},
            },
        ),
        patch(
            "app.services.semester_plan_suggestion_service._load_exact_term_offerings",
            new_callable=AsyncMock,
            return_value={
                "10001": {
                    "courseNumber": "10001",
                    "academicYear": 2025,
                    "semesterCode": 201,
                    "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
                }
            },
        ),
        patch(
            "app.services.semester_plan_suggestion_service.select_progress_aware_courses",
            return_value=selection,
        ),
    ):
        result = await suggest_semester_courses(
            database,
            "user-1",
            semester_code="2025-2",
            max_credits=18,
        )

    assert result["status"] == "ok"
    explanation = result["explanation"]
    assert explanation["partialPlan"] is True
    assert explanation["emptyPlan"] is False
    assert explanation["selectedCount"] == 1
    assert explanation["maxCredits"] == 18
    assert explanation["totalRecommendedCredits"] == 3


@pytest.mark.asyncio
async def test_suggest_semester_schedule_requires_active_courses():
    database = AsyncMock()
    with patch(
        "app.services.semester_plan_suggestion_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "ok"},
    ):
        result = await suggest_semester_schedule(
            database,
            "user-1",
            semester_code="2025-2",
            planned_courses=[{"courseId": "x", "courseNumber": "10001", "isActive": False}],
        )

    assert result["status"] == "validation_error"
    assert "At least one active planned course is required" in result["errors"][0]


@pytest.mark.asyncio
async def test_load_exact_term_offerings_returns_empty_for_no_numbers():
    from app.services.semester_plan_suggestion_service import _load_exact_term_offerings

    database = object()
    result = await _load_exact_term_offerings(
        database,
        [],
        academic_year=2025,
        semester_code=201,
    )
    assert result == {}


@pytest.mark.asyncio
async def test_suggest_semester_schedule_rejects_invalid_semester_code():
    database = object()
    with patch(
        "app.services.semester_plan_suggestion_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "ok"},
    ):
        result = await suggest_semester_schedule(
            database,
            "user-1",
            semester_code="2025-9",
            planned_courses=[{"courseId": "x", "courseNumber": "10001", "isActive": True}],
        )

    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_suggest_semester_schedule_returns_optimized_selections():
    database = AsyncMock()
    with (
        patch(
            "app.services.semester_plan_suggestion_service.load_planning_context",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch(
            "app.services.semester_plan_suggestion_service._load_exact_term_offerings",
            new_callable=AsyncMock,
            return_value={
                "10001": {
                    "courseNumber": "10001",
                    "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
                }
            },
        ),
        patch(
            "app.services.semester_plan_suggestion_service.optimize_schedule_for_planned_courses",
            return_value={
                "selections": [{"courseNumber": "10001", "selectedLessonEvents": []}],
                "skippedCourses": [],
                "examSummary": {"exams": []},
            },
        ),
    ):
        result = await suggest_semester_schedule(
            database,
            "user-1",
            semester_code="2025-2",
            planned_courses=[{"courseId": "x", "courseNumber": "10001", "isActive": True}],
        )

    assert result["status"] == "ok"
    assert result["selections"][0]["courseNumber"] == "10001"


@pytest.mark.asyncio
async def test_suggest_semester_schedule_propagates_planning_context_error():
    database = AsyncMock()
    with patch(
        "app.services.semester_plan_suggestion_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "degree_not_selected"},
    ):
        result = await suggest_semester_schedule(
            database,
            "user-1",
            semester_code="2025-2",
            planned_courses=[{"courseId": "x", "courseNumber": "10001", "isActive": True}],
        )

    assert result["status"] == "degree_not_selected"


@pytest.mark.asyncio
async def test_load_exact_term_offerings_indexes_canonical_number_aliases():
    from app.services.semester_plan_suggestion_service import _load_exact_term_offerings

    offering = {
        "courseNumber": "00940345",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
    }
    database = AsyncMock()
    with patch(
        "app.services.semester_plan_suggestion_service.catalog_repository.list_offerings_grouped_for_courses",
        new_callable=AsyncMock,
        return_value={"00940345": [offering]},
    ) as list_offerings:
        result = await _load_exact_term_offerings(
            database,
            ["0940345"],
            academic_year=2025,
            semester_code=201,
        )

    list_offerings.assert_awaited_once()
    queried_numbers = list_offerings.await_args.args[1]
    assert "0940345" in queried_numbers
    assert "00940345" in queried_numbers
    assert result["00940345"] == offering
    assert result["0940345"] == offering


def test_expand_course_numbers_for_lookup_skips_empty_values():
    from app.services.semester_plan_suggestion_service import _expand_course_numbers_for_lookup

    assert _expand_course_numbers_for_lookup(["", "  ", "0940345"]) == ["00940345", "0940345"]
