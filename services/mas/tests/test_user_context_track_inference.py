"""Tests for track slug inference and graduation error mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from app.clients.graduation_progress_client import graduation_error_code
from app.services.semester_catalog import semester_filename_for_plan_code
from app.services.track_registry import resolve_track_slug_from_program
from app.user_context import build_user_context


def test_resolve_track_slug_from_program_metadata() -> None:
    slug = resolve_track_slug_from_program(
        {
            "programCode": "009216-1-000",
            "metadata": {"wikiPage": "track-data-information-engineering"},
        }
    )
    assert slug == "track-data-information-engineering"


def test_semester_filename_for_plan_code() -> None:
    assert semester_filename_for_plan_code("2025-1") == "courses_2025_200.json"
    assert semester_filename_for_plan_code("2025-2") == "courses_2025_201.json"
    assert semester_filename_for_plan_code("invalid") is None


def test_graduation_error_code_maps_degree_not_selected() -> None:
    assert graduation_error_code(status_code=400, detail="Degree not selected on student profile") == (
        "degree_not_selected"
    )


def _database_with_degree(*, profile: dict, degree_program: dict | None) -> MagicMock:
    database = MagicMock()
    parsed_user_id = profile["userId"]

    def get_collection(name: str) -> MagicMock:
        collection = MagicMock()
        if name == "student_profiles":
            collection.find_one = AsyncMock(return_value=profile)
        elif name == "completed_courses":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[])
            collection.find = MagicMock(return_value=cursor)
        elif name == "courses":
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[])
            collection.find = MagicMock(return_value=cursor)
        elif name == "degree_programs":
            collection.find_one = AsyncMock(return_value=degree_program)
        else:
            raise KeyError(name)
        return collection

    database.__getitem__ = MagicMock(side_effect=get_collection)
    return database


@pytest.mark.asyncio
async def test_build_user_context_infers_track_slug_from_degree_program() -> None:
    user_id = str(ObjectId())
    degree_id = ObjectId()
    profile = {
        "userId": ObjectId(user_id),
        "degreeId": degree_id,
        "academicPath": {},
        "preferences": {},
    }
    degree_program = {
        "_id": degree_id,
        "programCode": "009216-1-000",
        "metadata": {"wikiPage": "track-data-information-engineering"},
        "status": "published",
    }

    context = await build_user_context(
        _database_with_degree(profile=profile, degree_program=degree_program),
        user_id,
    )

    assert context["track_slug"] == "track-data-information-engineering"
    assert "track_not_set" not in (context.get("data_quality") or {}).get("warnings", [])
