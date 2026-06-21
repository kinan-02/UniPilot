"""Unit tests for app/db/catalog_indexes.py — targets 100% branch coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.config import Settings
from app.db.catalog_indexes import ensure_catalog_indexes


def _make_mock_db(courses_col="courses", offerings_col="course_offerings", programs_col="degree_programs"):
    """Return a mock Motor database that records create_index calls per collection."""

    def make_collection():
        col = MagicMock()
        col.create_index = AsyncMock(return_value="index_name")
        return col

    collections: dict = {}

    def getitem(name: str):
        if name not in collections:
            collections[name] = make_collection()
        return collections[name]

    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=getitem)
    db._collections = collections
    return db


@pytest.mark.asyncio
async def test_ensure_catalog_indexes_creates_all_five_indexes() -> None:
    db = _make_mock_db()
    settings = Settings(
        environment="test",
        jwt_secret="test-secret",
        courses_collection="courses",
        course_offerings_collection="course_offerings",
        degree_programs_collection="degree_programs",
    )

    await ensure_catalog_indexes(db, settings=settings)

    courses_col = db["courses"]
    courses_col.create_index.assert_any_call(
        [("status", 1), ("courseNumber", 1)],
        name="courses_status_course_number",
    )
    courses_col.create_index.assert_any_call(
        [("status", 1), ("faculty", 1)],
        name="courses_status_faculty",
    )
    assert courses_col.create_index.await_count == 2

    offerings_col = db["course_offerings"]
    offerings_col.create_index.assert_any_call(
        [("status", 1), ("courseNumber", 1), ("semesterCode", 1), ("academicYear", 1)],
        name="offerings_status_course_term",
    )
    offerings_col.create_index.assert_any_call(
        [("status", 1), ("semesterCode", 1), ("academicYear", 1)],
        name="offerings_status_term",
    )
    assert offerings_col.create_index.await_count == 2

    programs_col = db["degree_programs"]
    programs_col.create_index.assert_any_call(
        [("status", 1), ("programCode", 1)],
        name="degree_programs_status_code",
    )
    assert programs_col.create_index.await_count == 1


@pytest.mark.asyncio
async def test_ensure_catalog_indexes_uses_custom_collection_names() -> None:
    """Settings with non-default collection names must be respected."""
    db = _make_mock_db()
    settings = Settings(
        environment="test",
        jwt_secret="test-secret",
        courses_collection="my_courses",
        course_offerings_collection="my_offerings",
        degree_programs_collection="my_programs",
    )

    await ensure_catalog_indexes(db, settings=settings)

    # verify correct collection names were accessed
    accessed = [call_args[0][0] for call_args in db.__getitem__.call_args_list]
    assert "my_courses" in accessed
    assert "my_offerings" in accessed
    assert "my_programs" in accessed


@pytest.mark.asyncio
async def test_ensure_catalog_indexes_calls_get_settings_when_none_passed(monkeypatch) -> None:
    """When settings=None the function must call get_settings()."""
    db = _make_mock_db()
    fake_settings = Settings(
        environment="test",
        jwt_secret="test-secret",
        courses_collection="courses",
        course_offerings_collection="course_offerings",
        degree_programs_collection="degree_programs",
    )
    monkeypatch.setattr("app.db.catalog_indexes.get_settings", lambda: fake_settings)

    await ensure_catalog_indexes(db)

    # If get_settings was used, the correct collections were accessed
    accessed = [call_args[0][0] for call_args in db.__getitem__.call_args_list]
    assert "courses" in accessed
