"""Unit tests for per-student MongoDB context loading."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from app.user_context import build_user_context


def _collection(*, find_one=None, find_items=None) -> MagicMock:
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=find_one)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=find_items or [])
    collection.find = MagicMock(return_value=cursor)
    return collection


def _database(
    *,
    profile: dict | None = None,
    completed: list | None = None,
    courses: list | None = None,
) -> MagicMock:
    database = MagicMock()

    def get_collection(name: str) -> MagicMock:
        if name == "student_profiles":
            return _collection(find_one=profile)
        if name == "completed_courses":
            return _collection(find_items=completed or [])
        if name == "courses":
            return _collection(find_items=courses or [])
        raise KeyError(name)

    database.__getitem__ = MagicMock(side_effect=get_collection)
    return database


@pytest.mark.asyncio
async def test_build_user_context_invalid_user_id() -> None:
    context = await build_user_context(_database(), "not-an-object-id")
    assert context["user_id"] == "not-an-object-id"
    assert context["completed_courses"] == []


@pytest.mark.asyncio
async def test_build_user_context_without_profile() -> None:
    user_id = str(ObjectId())
    course_id = ObjectId()
    context = await build_user_context(
        _database(
            completed=[{"courseId": course_id, "grade": 82, "attempt": 1}],
            courses=[{"_id": course_id, "courseNumber": "00140008"}],
        ),
        user_id,
    )
    assert context["completed_courses"] == ["00140008"]
    assert "track_slug" not in context


@pytest.mark.asyncio
async def test_build_user_context_with_profile_and_preferences() -> None:
    user_id = str(ObjectId())
    course_id = ObjectId()
    profile = {
        "userId": ObjectId(user_id),
        "displayName": "Ada",
        "facultyId": "cs",
        "catalogYear": 2024,
        "degreeId": "bsc-cs",
        "currentSemesterCode": "2025-1",
        "preferences": {"avoidDays": ["שישי"]},
        "academicPath": {"trackSlug": "  cs-core  "},
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }

    context = await build_user_context(
        _database(
            profile=profile,
            completed=[{"courseId": course_id, "grade": 82, "attempt": 1}],
            courses=[{"_id": course_id, "courseNumber": "00940139"}],
        ),
        user_id,
    )

    assert context["track_slug"] == "cs-core"
    assert context["display_name"] == "Ada"
    assert context["plan_semester_code"] == "2025-1"
    assert context["preferences"] == {"avoidDays": ["שישי"]}
    assert context["completed_courses"] == ["00940139"]


@pytest.mark.asyncio
async def test_build_user_context_ignores_failed_latest_attempt() -> None:
    user_id = str(ObjectId())
    course_id = ObjectId()
    context = await build_user_context(
        _database(
            completed=[
                {"courseId": course_id, "grade": 82, "attempt": 1, "semesterCode": "2024-1"},
                {"courseId": course_id, "grade": 40, "attempt": 2, "semesterCode": "2025-1"},
            ],
            courses=[{"_id": course_id, "courseNumber": "00940139"}],
        ),
        user_id,
    )
    assert context["completed_courses"] == []
