"""Unit tests for completed_course_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.completed_course_repository import (
    _format_datetime,
    build_completed_course_document,
    create_completed_course,
    delete_completed_course_by_id_and_user_id,
    find_all_completed_courses_by_user_id,
    find_completed_course_by_id_and_user_id,
    find_completed_courses_by_user_id,
    parse_object_id,
    to_public_completed_course,
    update_completed_course_by_id_and_user_id,
)

VALID_USER_ID = str(ObjectId())
VALID_COURSE_ID = str(ObjectId())

VALID_RECORD_DATA = {
    "courseId": VALID_COURSE_ID,
    "semesterCode": "2024-1",
    "grade": 85,
    "gradePoints": None,
    "creditsEarned": 3.0,
    "attempt": 1,
    "source": "manual",
}


# ---------------------------------------------------------------------------
# parse_object_id (mirrors semester plan repo — verify independently)
# ---------------------------------------------------------------------------

def test_parse_object_id_returns_none_for_none():
    assert parse_object_id(None) is None


def test_parse_object_id_returns_none_for_bad_string():
    assert parse_object_id("bad-id") is None


def test_parse_object_id_parses_valid_id():
    oid = ObjectId()
    assert parse_object_id(str(oid)) == oid


# ---------------------------------------------------------------------------
# build_completed_course_document
# ---------------------------------------------------------------------------

def test_build_completed_course_document_valid():
    doc = build_completed_course_document(VALID_USER_ID, VALID_RECORD_DATA)
    assert isinstance(doc["userId"], ObjectId)
    assert isinstance(doc["courseId"], ObjectId)
    assert doc["semesterCode"] == "2024-1"
    assert doc["grade"] == 85
    assert doc["creditsEarned"] == 3.0
    assert doc["attempt"] == 1
    assert doc["source"] == "manual"
    assert isinstance(doc["createdAt"], datetime)


def test_build_completed_course_document_defaults_attempt_to_1():
    data = dict(VALID_RECORD_DATA)
    data.pop("attempt")
    doc = build_completed_course_document(VALID_USER_ID, data)
    assert doc["attempt"] == 1


def test_build_completed_course_document_raises_on_invalid_user_id():
    with pytest.raises(ValueError, match="Invalid user id"):
        build_completed_course_document("bad-id", VALID_RECORD_DATA)


def test_build_completed_course_document_raises_on_invalid_course_id():
    data = {**VALID_RECORD_DATA, "courseId": "bad-id"}
    with pytest.raises(ValueError, match="Invalid course id"):
        build_completed_course_document(VALID_USER_ID, data)


# ---------------------------------------------------------------------------
# _format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_converts_to_iso_z():
    dt = datetime(2025, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
    assert _format_datetime(dt) == "2025-03-10T14:00:00Z"


def test_format_datetime_passthrough():
    assert _format_datetime("2025-01-01") == "2025-01-01"


# ---------------------------------------------------------------------------
# to_public_completed_course
# ---------------------------------------------------------------------------

def test_to_public_completed_course_returns_none_for_none():
    assert to_public_completed_course(None) is None


def test_to_public_completed_course_basic_fields():
    doc = build_completed_course_document(VALID_USER_ID, VALID_RECORD_DATA)
    doc["_id"] = ObjectId()
    result = to_public_completed_course(doc)
    assert result is not None
    assert result["grade"] == 85
    assert result["semesterCode"] == "2024-1"
    assert result["creditsEarned"] == 3.0
    assert result["attempt"] == 1
    assert result["source"] == "manual"
    assert result["courseNumber"] is None
    assert result["courseTitle"] is None


def test_to_public_completed_course_uses_course_summary():
    doc = build_completed_course_document(VALID_USER_ID, VALID_RECORD_DATA)
    doc["_id"] = ObjectId()
    summary = {"number": "00940101", "title": "Algebra"}
    result = to_public_completed_course(doc, course_summary=summary)
    assert result is not None
    assert result["courseNumber"] == "00940101"
    assert result["courseTitle"] == "Algebra"


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_completed_course_returns_document_with_id(mongo_database):
    result = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    assert "_id" in result
    assert result["grade"] == 85


@pytest.mark.asyncio
async def test_find_completed_courses_by_user_id_returns_created(mongo_database):
    await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    result = await find_completed_courses_by_user_id(mongo_database, VALID_USER_ID)
    assert result["total"] == 1
    assert len(result["records"]) == 1
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_find_completed_courses_by_user_id_returns_empty_for_unknown(mongo_database):
    result = await find_completed_courses_by_user_id(mongo_database, str(ObjectId()))
    assert result["total"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_find_completed_courses_by_user_id_returns_empty_for_invalid_id(mongo_database):
    result = await find_completed_courses_by_user_id(mongo_database, "bad-id")
    assert result["total"] == 0
    assert result["records"] == []


@pytest.mark.asyncio
async def test_find_all_completed_courses_by_user_id_returns_list(mongo_database):
    course_id2 = str(ObjectId())
    await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    await create_completed_course(
        mongo_database, VALID_USER_ID, {**VALID_RECORD_DATA, "courseId": course_id2}
    )
    records = await find_all_completed_courses_by_user_id(mongo_database, VALID_USER_ID)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_find_all_completed_courses_returns_empty_for_invalid_id(mongo_database):
    records = await find_all_completed_courses_by_user_id(mongo_database, "bad-id")
    assert records == []


@pytest.mark.asyncio
async def test_find_completed_course_by_id_and_user_id(mongo_database):
    created = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    record_id = str(created["_id"])

    found = await find_completed_course_by_id_and_user_id(mongo_database, record_id, VALID_USER_ID)
    assert found is not None
    assert found["grade"] == 85


@pytest.mark.asyncio
async def test_find_completed_course_by_id_returns_none_for_wrong_user(mongo_database):
    created = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    record_id = str(created["_id"])

    found = await find_completed_course_by_id_and_user_id(mongo_database, record_id, str(ObjectId()))
    assert found is None


@pytest.mark.asyncio
async def test_find_completed_course_by_id_returns_none_for_invalid_ids(mongo_database):
    assert await find_completed_course_by_id_and_user_id(mongo_database, "bad", VALID_USER_ID) is None
    assert await find_completed_course_by_id_and_user_id(mongo_database, str(ObjectId()), "bad") is None


@pytest.mark.asyncio
async def test_update_completed_course_updates_grade(mongo_database):
    created = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    record_id = str(created["_id"])

    result = await update_completed_course_by_id_and_user_id(
        mongo_database, record_id, VALID_USER_ID, {"grade": 90}
    )
    assert result["status"] == "updated"
    assert result["record"]["grade"] == 90


@pytest.mark.asyncio
async def test_update_completed_course_returns_not_found_for_missing(mongo_database):
    result = await update_completed_course_by_id_and_user_id(
        mongo_database, str(ObjectId()), VALID_USER_ID, {"grade": 90}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_update_completed_course_returns_not_editable_for_non_manual(mongo_database):
    non_manual_data = {**VALID_RECORD_DATA, "source": "import"}
    created = await create_completed_course(mongo_database, VALID_USER_ID, non_manual_data)
    record_id = str(created["_id"])

    result = await update_completed_course_by_id_and_user_id(
        mongo_database, record_id, VALID_USER_ID, {"grade": 70}
    )
    assert result["status"] == "not_editable"


@pytest.mark.asyncio
async def test_delete_completed_course_returns_deleted(mongo_database):
    created = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    record_id = str(created["_id"])

    result = await delete_completed_course_by_id_and_user_id(mongo_database, record_id, VALID_USER_ID)
    assert result["status"] == "deleted"

    found = await find_completed_course_by_id_and_user_id(mongo_database, record_id, VALID_USER_ID)
    assert found is None


@pytest.mark.asyncio
async def test_delete_completed_course_returns_not_found_for_missing(mongo_database):
    result = await delete_completed_course_by_id_and_user_id(
        mongo_database, str(ObjectId()), VALID_USER_ID
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_delete_completed_course_returns_not_editable_for_non_manual(mongo_database):
    non_manual_data = {**VALID_RECORD_DATA, "source": "import"}
    created = await create_completed_course(mongo_database, VALID_USER_ID, non_manual_data)
    record_id = str(created["_id"])

    result = await delete_completed_course_by_id_and_user_id(mongo_database, record_id, VALID_USER_ID)
    assert result["status"] == "not_editable"


@pytest.mark.asyncio
async def test_find_completed_courses_pagination(mongo_database):
    for i in range(5):
        cid = str(ObjectId())
        await create_completed_course(
            mongo_database, VALID_USER_ID, {**VALID_RECORD_DATA, "courseId": cid}
        )

    result = await find_completed_courses_by_user_id(mongo_database, VALID_USER_ID, page=1, limit=3)
    assert len(result["records"]) == 3
    assert result["total"] == 5


@pytest.mark.asyncio
async def test_update_completed_course_updates_semester_code_and_grade_points(mongo_database):
    """semesterCode and gradePoints update paths (lines 190, 194)."""
    created = await create_completed_course(mongo_database, VALID_USER_ID, VALID_RECORD_DATA)
    record_id = str(created["_id"])

    result = await update_completed_course_by_id_and_user_id(
        mongo_database,
        record_id,
        VALID_USER_ID,
        {"semesterCode": "2026-1", "gradePoints": 95.0},
    )
    assert result["status"] == "updated"
    assert result["record"]["semesterCode"] == "2026-1"
    assert result["record"]["gradePoints"] == 95.0


@pytest.mark.asyncio
async def test_update_completed_course_returns_not_found_after_race_condition(mongo_database):
    """update returns None → status not_found (line 211). Use mock collection."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId

    existing = {
        "_id": ObjectId(),
        "userId": ObjectId(),
        "source": "manual",
        "courseId": ObjectId(),
        "grade": 70,
        "creditsEarned": 3.0,
    }

    # Mock both the find function and the collection's find_one_and_update
    mock_collection = MagicMock()
    mock_collection.find_one_and_update = AsyncMock(return_value=None)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch(
        "app.repositories.completed_course_repository.find_completed_course_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=existing,
    ):
        result = await update_completed_course_by_id_and_user_id(
            mock_db,
            str(existing["_id"]),
            str(existing["userId"]),
            {"grade": 80},
        )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_delete_completed_course_returns_not_found_when_delete_count_zero(mongo_database):
    """delete_one returns deleted_count=0 → not_found (line 245). Use mock collection."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId

    existing = {
        "_id": ObjectId(),
        "userId": ObjectId(),
        "source": "manual",
        "courseId": ObjectId(),
        "grade": 70,
        "creditsEarned": 3.0,
    }

    class FakeDeleteResult:
        deleted_count = 0

    mock_collection = MagicMock()
    mock_collection.delete_one = AsyncMock(return_value=FakeDeleteResult())

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch(
        "app.repositories.completed_course_repository.find_completed_course_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=existing,
    ):
        result = await delete_completed_course_by_id_and_user_id(
            mock_db,
            str(existing["_id"]),
            str(existing["userId"]),
        )
    assert result["status"] == "not_found"
