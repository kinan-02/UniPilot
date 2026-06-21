"""Unit tests for semester_plan_repository — sync helpers and async CRUD via mongomock."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.semester_plan_repository import (
    _format_datetime,
    _serialize_semester,
    build_semester_plan_document,
    create_semester_plan,
    create_semester_plan_version_from_source,
    find_semester_plan_by_id_and_user_id,
    find_semester_plan_by_share_token,
    find_semester_plans_by_user_id,
    parse_object_id,
    to_public_semester_plan,
    to_public_semester_plan_summary,
    to_public_shared_semester_plan,
    update_semester_plan_by_id_and_user_id,
)

VALID_USER_ID = str(ObjectId())
VALID_PLAN_DATA = {
    "name": "Test Plan",
    "status": "draft",
    "version": 1,
    "plannerType": "manual",
    "assumptions": {"createdBy": "manual"},
    "explanation": {"summary": "My plan"},
    "semesters": [
        {
            "semesterCode": "2025-2",
            "goalCredits": 15.0,
            "order": 1,
            "plannedCourses": [
                {"courseId": "cid1", "credits": 4, "isActive": True}
            ],
            "maybeCourses": [],
            "notes": "",
            "constraintsSnapshot": {},
        }
    ],
}


# ---------------------------------------------------------------------------
# parse_object_id
# ---------------------------------------------------------------------------

def test_parse_object_id_returns_none_for_none():
    assert parse_object_id(None) is None


def test_parse_object_id_returns_none_for_invalid():
    assert parse_object_id("not-an-object-id") is None


def test_parse_object_id_parses_valid_hex():
    oid = ObjectId()
    assert parse_object_id(str(oid)) == oid


# ---------------------------------------------------------------------------
# build_semester_plan_document
# ---------------------------------------------------------------------------

def test_build_semester_plan_document_returns_expected_shape():
    doc = build_semester_plan_document(VALID_USER_ID, VALID_PLAN_DATA)
    assert doc["name"] == "Test Plan"
    assert doc["status"] == "draft"
    assert doc["version"] == 1
    assert doc["plannerType"] == "manual"
    assert isinstance(doc["userId"], ObjectId)
    assert isinstance(doc["createdAt"], datetime)
    assert isinstance(doc["updatedAt"], datetime)


def test_build_semester_plan_document_defaults_status_to_draft():
    data = dict(VALID_PLAN_DATA)
    data.pop("status")
    doc = build_semester_plan_document(VALID_USER_ID, data)
    assert doc["status"] == "draft"


def test_build_semester_plan_document_raises_on_invalid_user_id():
    with pytest.raises(ValueError, match="Invalid user id"):
        build_semester_plan_document("not-valid", VALID_PLAN_DATA)


# ---------------------------------------------------------------------------
# _format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_converts_datetime_to_iso_z():
    dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    result = _format_datetime(dt)
    assert result == "2025-01-15T10:30:00Z"


def test_format_datetime_passthrough_non_datetime():
    assert _format_datetime("already-string") == "already-string"
    assert _format_datetime(None) is None


# ---------------------------------------------------------------------------
# _serialize_semester
# ---------------------------------------------------------------------------

def test_serialize_semester_includes_weekly_schedule_when_present():
    semester = {
        "semesterCode": "2025-2",
        "goalCredits": 15,
        "order": 1,
        "plannedCourses": [],
        "maybeCourses": [],
        "notes": "x",
        "constraintsSnapshot": {},
        "weeklySchedule": {"entries": []},
    }
    result = _serialize_semester(semester)
    assert "weeklySchedule" in result
    assert result["weeklySchedule"] == {"entries": []}


def test_serialize_semester_excludes_weekly_schedule_when_absent():
    semester = {
        "semesterCode": "2025-2",
        "goalCredits": 15,
        "order": 1,
        "plannedCourses": [],
        "maybeCourses": [],
        "notes": "",
        "constraintsSnapshot": {},
    }
    result = _serialize_semester(semester)
    assert "weeklySchedule" not in result


def test_serialize_semester_includes_custom_events_when_present():
    semester = {
        "semesterCode": "2025-2",
        "goalCredits": 15,
        "order": 1,
        "plannedCourses": [],
        "maybeCourses": [],
        "notes": "",
        "constraintsSnapshot": {},
        "customEvents": [{"title": "Holiday"}],
    }
    result = _serialize_semester(semester)
    assert "customEvents" in result


# ---------------------------------------------------------------------------
# to_public_semester_plan_summary
# ---------------------------------------------------------------------------

def test_to_public_semester_plan_summary_returns_none_for_none():
    assert to_public_semester_plan_summary(None) is None


def test_to_public_semester_plan_summary_extracts_fields():
    doc = {
        "_id": ObjectId(),
        "name": "My Plan",
        "status": "draft",
        "version": 1,
        "plannerType": "manual",
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseId": "c1"}, {"courseId": "c2"}],
            }
        ],
        "explanation": {"totalRecommendedCredits": 12, "summary": "ok"},
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }
    result = to_public_semester_plan_summary(doc)
    assert result is not None
    assert result["name"] == "My Plan"
    assert result["recommendedCourseCount"] == 2
    assert result["totalRecommendedCredits"] == 12
    assert result["createdAt"] == "2025-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# to_public_semester_plan
# ---------------------------------------------------------------------------

def test_to_public_semester_plan_returns_none_for_none():
    assert to_public_semester_plan(None) is None


def test_to_public_semester_plan_includes_share_token_when_enabled():
    doc = {
        "_id": ObjectId(),
        "name": "Plan",
        "status": "active",
        "version": 2,
        "basePlanId": None,
        "plannerType": "manual",
        "assumptions": {},
        "explanation": {},
        "semesters": [],
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "shareEnabled": True,
        "shareToken": "abc123",
    }
    result = to_public_semester_plan(doc)
    assert result is not None
    assert result["shareToken"] == "abc123"
    assert result["shareEnabled"] is True


def test_to_public_semester_plan_omits_share_token_when_disabled():
    doc = {
        "_id": ObjectId(),
        "name": "Plan",
        "status": "draft",
        "version": 1,
        "basePlanId": None,
        "plannerType": "manual",
        "assumptions": {},
        "explanation": {},
        "semesters": [],
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "shareEnabled": False,
    }
    result = to_public_semester_plan(doc)
    assert result is not None
    assert "shareToken" not in result


def test_to_public_semester_plan_stringifies_base_plan_id():
    base_id = ObjectId()
    doc = {
        "_id": ObjectId(),
        "name": "Plan",
        "status": "draft",
        "version": 2,
        "basePlanId": base_id,
        "plannerType": "manual",
        "assumptions": {},
        "explanation": {},
        "semesters": [],
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "shareEnabled": False,
    }
    result = to_public_semester_plan(doc)
    assert result is not None
    assert result["basePlanId"] == str(base_id)


# ---------------------------------------------------------------------------
# to_public_shared_semester_plan
# ---------------------------------------------------------------------------

def test_to_public_shared_semester_plan_adds_read_only():
    doc = {
        "_id": ObjectId(),
        "name": "Plan",
        "status": "active",
        "version": 1,
        "basePlanId": None,
        "plannerType": "manual",
        "assumptions": {},
        "explanation": {},
        "semesters": [],
        "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "shareEnabled": True,
        "shareToken": "tok123",
    }
    result = to_public_shared_semester_plan(doc)
    assert result is not None
    assert result["readOnly"] is True
    assert "shareToken" not in result


def test_to_public_shared_semester_plan_returns_none_for_none():
    assert to_public_shared_semester_plan(None) is None


# ---------------------------------------------------------------------------
# Async CRUD via mongomock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_semester_plan_returns_document_with_id(mongo_database):
    result = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    assert "_id" in result
    assert result["name"] == "Test Plan"
    assert result["status"] == "draft"


@pytest.mark.asyncio
async def test_find_semester_plans_by_user_id_returns_created_plans(mongo_database):
    await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    await create_semester_plan(mongo_database, VALID_USER_ID, {**VALID_PLAN_DATA, "name": "Plan 2"})

    result = await find_semester_plans_by_user_id(mongo_database, VALID_USER_ID)
    assert result["total"] == 2
    assert len(result["plans"]) == 2
    assert result["page"] == 1
    assert result["limit"] == 50


@pytest.mark.asyncio
async def test_find_semester_plans_by_user_id_returns_empty_for_unknown(mongo_database):
    result = await find_semester_plans_by_user_id(mongo_database, str(ObjectId()))
    assert result["total"] == 0
    assert result["plans"] == []


@pytest.mark.asyncio
async def test_find_semester_plans_by_user_id_returns_empty_for_invalid(mongo_database):
    result = await find_semester_plans_by_user_id(mongo_database, "bad-id")
    assert result["total"] == 0
    assert result["plans"] == []


@pytest.mark.asyncio
async def test_find_semester_plan_by_id_and_user_id_returns_plan(mongo_database):
    created = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    plan_id = str(created["_id"])

    result = await find_semester_plan_by_id_and_user_id(mongo_database, plan_id, VALID_USER_ID)
    assert result is not None
    assert result["name"] == "Test Plan"


@pytest.mark.asyncio
async def test_find_semester_plan_by_id_and_user_id_returns_none_for_wrong_user(mongo_database):
    created = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    plan_id = str(created["_id"])

    result = await find_semester_plan_by_id_and_user_id(mongo_database, plan_id, str(ObjectId()))
    assert result is None


@pytest.mark.asyncio
async def test_find_semester_plan_by_id_and_user_id_returns_none_for_invalid_ids(mongo_database):
    assert await find_semester_plan_by_id_and_user_id(mongo_database, "bad", VALID_USER_ID) is None
    assert await find_semester_plan_by_id_and_user_id(mongo_database, str(ObjectId()), "bad") is None


@pytest.mark.asyncio
async def test_update_semester_plan_by_id_and_user_id_updates_name(mongo_database):
    created = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    plan_id = str(created["_id"])

    updated = await update_semester_plan_by_id_and_user_id(
        mongo_database, plan_id, VALID_USER_ID, {"name": "Updated Name"}
    )
    assert updated is not None
    assert updated["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_semester_plan_by_id_and_user_id_returns_none_for_invalid(mongo_database):
    result = await update_semester_plan_by_id_and_user_id(
        mongo_database, "bad-id", VALID_USER_ID, {"name": "x"}
    )
    assert result is None


@pytest.mark.asyncio
async def test_create_semester_plan_version_from_source_increments_version(mongo_database):
    source = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    new_version = await create_semester_plan_version_from_source(
        mongo_database, VALID_USER_ID, source
    )
    assert new_version["version"] == 2
    assert "forkedFromPlanId" in new_version["assumptions"]


@pytest.mark.asyncio
async def test_create_semester_plan_version_from_source_uses_custom_name(mongo_database):
    source = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    new_version = await create_semester_plan_version_from_source(
        mongo_database, VALID_USER_ID, source, name="My Fork"
    )
    assert new_version["name"] == "My Fork"


@pytest.mark.asyncio
async def test_create_semester_plan_version_raises_on_invalid_user(mongo_database):
    source = await create_semester_plan(mongo_database, VALID_USER_ID, VALID_PLAN_DATA)
    with pytest.raises(ValueError, match="Invalid user id"):
        await create_semester_plan_version_from_source(mongo_database, "bad-id", source)


@pytest.mark.asyncio
async def test_find_semester_plan_by_share_token_returns_none_when_not_found(mongo_database):
    result = await find_semester_plan_by_share_token(mongo_database, "unknown-token")
    assert result is None


@pytest.mark.asyncio
async def test_find_semester_plan_by_share_token_returns_none_for_empty(mongo_database):
    result = await find_semester_plan_by_share_token(mongo_database, "")
    assert result is None


@pytest.mark.asyncio
async def test_find_semester_plans_pagination(mongo_database):
    for i in range(5):
        await create_semester_plan(mongo_database, VALID_USER_ID, {**VALID_PLAN_DATA, "name": f"Plan {i}"})

    page1 = await find_semester_plans_by_user_id(mongo_database, VALID_USER_ID, page=1, limit=3)
    assert len(page1["plans"]) == 3
    assert page1["total"] == 5
    assert page1["limit"] == 3
