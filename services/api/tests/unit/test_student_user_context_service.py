"""Unit tests for canonical student user context service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.student_user_context_service import build_student_user_context


@pytest.mark.asyncio
async def test_build_student_user_context_uses_course_number_field() -> None:
    course_id = ObjectId()
    profile = {
        "userId": ObjectId(),
        "degreeId": ObjectId(),
        "facultyId": "009",
        "catalogYear": 2025,
        "currentSemesterCode": "2025-1",
        "displayName": "Ada",
        "academicPath": {"trackSlug": "track-data-information-engineering"},
        "preferences": {},
    }
    database = AsyncMock()

    with (
        patch(
            "app.services.student_user_context_service.find_student_profile_by_user_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "app.services.student_user_context_service.find_all_completed_courses_by_user_id",
            new=AsyncMock(
                return_value=[
                    {
                        "courseId": course_id,
                        "grade": 82,
                        "creditsEarned": 3.0,
                        "attempt": 1,
                    }
                ]
            ),
        ),
        patch(
            "app.services.student_user_context_service.find_courses_by_ids",
            new=AsyncMock(
                return_value=[
                    {
                        "_id": course_id,
                        "courseNumber": "00940139",
                        "title": "Algorithms",
                    }
                ]
            ),
        ),
    ):
        context = await build_student_user_context(database, str(ObjectId()))

    assert context["completed_courses"] == ["00940139"]
    assert context["track_slug"] == "track-data-information-engineering"
    assert context["data_quality"]["ok"] is True


@pytest.mark.asyncio
async def test_build_student_user_context_flags_missing_profile() -> None:
    database = AsyncMock()

    with (
        patch(
            "app.services.student_user_context_service.find_student_profile_by_user_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.student_user_context_service.find_all_completed_courses_by_user_id",
            new=AsyncMock(return_value=[]),
        ),
    ):
        context = await build_student_user_context(database, str(ObjectId()))

    assert "profile_not_found" in context["data_quality"]["warnings"]
    assert "no_transcript_records" in context["data_quality"]["warnings"]
