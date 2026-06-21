"""Unit tests for student_profile_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.student_profile_repository import (
    _format_datetime,
    build_profile_document,
    create_student_profile,
    delete_student_profile_by_user_id,
    find_student_profile_by_user_id,
    parse_object_id,
    to_public_student_profile,
    update_student_profile_by_user_id,
)

VALID_USER_ID = str(ObjectId())

VALID_PROFILE_DATA = {
    "institutionId": "technion",
    "programType": "BSc",
    "catalogYear": 2024,
    "currentSemesterCode": "2024-2",
    "preferences": {"maxCreditsPerSemester": 18},
}


# ---------------------------------------------------------------------------
# parse_object_id
# ---------------------------------------------------------------------------

def test_parse_object_id_returns_none_for_none():
    assert parse_object_id(None) is None


def test_parse_object_id_returns_none_for_invalid():
    assert parse_object_id("not-valid") is None


def test_parse_object_id_parses_valid():
    oid = ObjectId()
    assert parse_object_id(str(oid)) == oid


# ---------------------------------------------------------------------------
# build_profile_document
# ---------------------------------------------------------------------------

def test_build_profile_document_returns_expected_shape():
    doc = build_profile_document(VALID_USER_ID, VALID_PROFILE_DATA)
    assert isinstance(doc["userId"], ObjectId)
    assert doc["institutionId"] == "technion"
    assert doc["programType"] == "BSc"
    assert doc["catalogYear"] == 2024
    assert doc["currentSemesterCode"] == "2024-2"
    assert doc["revision"] == 1
    assert isinstance(doc["createdAt"], datetime)


def test_build_profile_document_handles_degree_id():
    degree_id = str(ObjectId())
    data = {**VALID_PROFILE_DATA, "degreeId": degree_id}
    doc = build_profile_document(VALID_USER_ID, data)
    assert isinstance(doc["degreeId"], ObjectId)


def test_build_profile_document_handles_no_degree_id():
    doc = build_profile_document(VALID_USER_ID, VALID_PROFILE_DATA)
    assert doc["degreeId"] is None


def test_build_profile_document_raises_on_invalid_user_id():
    with pytest.raises(ValueError, match="Invalid user id"):
        build_profile_document("bad-id", VALID_PROFILE_DATA)


# ---------------------------------------------------------------------------
# _format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_converts_to_iso_z():
    dt = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert _format_datetime(dt) == "2025-06-01T00:00:00Z"


def test_format_datetime_passthrough_non_datetime():
    assert _format_datetime("2025-01") == "2025-01"


# ---------------------------------------------------------------------------
# to_public_student_profile
# ---------------------------------------------------------------------------

def test_to_public_student_profile_returns_none_for_none():
    assert to_public_student_profile(None) is None


def test_to_public_student_profile_extracts_fields():
    doc = {
        "_id": ObjectId(),
        "userId": ObjectId(VALID_USER_ID),
        "institutionId": "technion",
        "programType": "BSc",
        "degreeId": None,
        "catalogYear": 2024,
        "currentSemesterCode": "2024-2",
        "preferences": {},
        "revision": 1,
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }
    result = to_public_student_profile(doc)
    assert result is not None
    assert result["institutionId"] == "technion"
    assert result["degreeId"] is None
    assert result["revision"] == 1
    assert result["createdAt"] == "2025-01-01T00:00:00Z"


def test_to_public_student_profile_stringifies_degree_id():
    degree_oid = ObjectId()
    doc = {
        "_id": ObjectId(),
        "userId": ObjectId(VALID_USER_ID),
        "institutionId": "technion",
        "programType": "BSc",
        "degreeId": degree_oid,
        "catalogYear": 2024,
        "currentSemesterCode": "2024-2",
        "preferences": {},
        "revision": 1,
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    result = to_public_student_profile(doc)
    assert result is not None
    assert result["degreeId"] == str(degree_oid)


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_student_profile_returns_document_with_id(mongo_database):
    result = await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    assert "_id" in result
    assert result["institutionId"] == "technion"
    assert result["revision"] == 1


@pytest.mark.asyncio
async def test_find_student_profile_by_user_id_returns_created(mongo_database):
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    result = await find_student_profile_by_user_id(mongo_database, VALID_USER_ID)
    assert result is not None
    assert result["institutionId"] == "technion"


@pytest.mark.asyncio
async def test_find_student_profile_by_user_id_returns_none_for_unknown(mongo_database):
    result = await find_student_profile_by_user_id(mongo_database, str(ObjectId()))
    assert result is None


@pytest.mark.asyncio
async def test_find_student_profile_by_user_id_returns_none_for_invalid(mongo_database):
    result = await find_student_profile_by_user_id(mongo_database, "bad-id")
    assert result is None


@pytest.mark.asyncio
async def test_update_student_profile_by_user_id_updates_catalog_year(mongo_database):
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    result = await update_student_profile_by_user_id(
        mongo_database, VALID_USER_ID, {"catalogYear": 2025}
    )
    assert result is not None
    assert result["catalogYear"] == 2025


@pytest.mark.asyncio
async def test_update_student_profile_updates_degree_id(mongo_database):
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    degree_id = str(ObjectId())
    result = await update_student_profile_by_user_id(
        mongo_database, VALID_USER_ID, {"degreeId": degree_id}
    )
    assert result is not None
    assert result["degreeId"] == ObjectId(degree_id)


@pytest.mark.asyncio
async def test_update_student_profile_clears_degree_id_when_none(mongo_database):
    degree_id = str(ObjectId())
    data = {**VALID_PROFILE_DATA, "degreeId": degree_id}
    await create_student_profile(mongo_database, VALID_USER_ID, data)
    result = await update_student_profile_by_user_id(
        mongo_database, VALID_USER_ID, {"degreeId": None}
    )
    assert result is not None
    assert result["degreeId"] is None


@pytest.mark.asyncio
async def test_update_student_profile_returns_none_for_invalid_user_id(mongo_database):
    result = await update_student_profile_by_user_id(mongo_database, "bad-id", {"catalogYear": 2025})
    assert result is None


@pytest.mark.asyncio
async def test_update_student_profile_updates_preferences(mongo_database):
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    result = await update_student_profile_by_user_id(
        mongo_database, VALID_USER_ID, {"preferences": {"maxCreditsPerSemester": 20}}
    )
    assert result is not None
    assert result["preferences"]["maxCreditsPerSemester"] == 20


@pytest.mark.asyncio
async def test_delete_student_profile_by_user_id_deletes(mongo_database):
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    deleted_count = await delete_student_profile_by_user_id(mongo_database, VALID_USER_ID)
    assert deleted_count == 1

    result = await find_student_profile_by_user_id(mongo_database, VALID_USER_ID)
    assert result is None


@pytest.mark.asyncio
async def test_delete_student_profile_returns_zero_for_missing(mongo_database):
    count = await delete_student_profile_by_user_id(mongo_database, str(ObjectId()))
    assert count == 0


@pytest.mark.asyncio
async def test_delete_student_profile_returns_zero_for_invalid_id(mongo_database):
    count = await delete_student_profile_by_user_id(mongo_database, "bad-id")
    assert count == 0


@pytest.mark.asyncio
async def test_update_student_profile_updates_institution_id(mongo_database):
    """institutionId update path (line 92)."""
    await create_student_profile(mongo_database, VALID_USER_ID, VALID_PROFILE_DATA)
    result = await update_student_profile_by_user_id(
        mongo_database,
        VALID_USER_ID,
        {"institutionId": "tau"},
    )
    assert result is not None
    assert result["institutionId"] == "tau"
