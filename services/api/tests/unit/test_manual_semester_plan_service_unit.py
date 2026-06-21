"""Unit tests for manual_semester_plan_service — sync helpers and async flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from app.services.manual_semester_plan_service import (
    _course_credits,
    _course_title,
    _normalize_course_id,
    build_manual_plan_document,
    build_manual_planned_course,
    collect_course_ids_across_semesters,
    is_course_active,
    validate_status_transition,
)

# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------

def test_normalize_course_id_stringifies():
    oid = ObjectId()
    assert _normalize_course_id(oid) == str(oid)
    assert _normalize_course_id("abc") == "abc"
    assert _normalize_course_id(123) == "123"


def test_course_title_prefers_hebrew():
    course = {"titleHebrew": "אלגוריתמים", "title": "Algorithms"}
    assert _course_title(course) == "אלגוריתמים"


def test_course_title_falls_back_to_title():
    course = {"title": "Algorithms"}
    assert _course_title(course) == "Algorithms"


def test_course_title_returns_empty_string_when_missing():
    assert _course_title({}) == ""


def test_course_credits_rounds_correctly():
    assert _course_credits({"credits": 3.0}) == 3.0
    assert _course_credits({"credits": None}) == 0.0
    assert _course_credits({}) == 0.0


def test_is_course_active_defaults_to_true():
    assert is_course_active({}) is True
    assert is_course_active({"isActive": True}) is True


def test_is_course_active_false_when_explicitly_set():
    assert is_course_active({"isActive": False}) is False


def test_validate_status_transition_returns_none_when_no_next_status():
    assert validate_status_transition("draft", None) is None


def test_validate_status_transition_returns_none_for_valid_transition():
    assert validate_status_transition("draft", "active") is None
    assert validate_status_transition("active", "draft") is None


def test_validate_status_transition_blocks_invalid_status():
    err = validate_status_transition("draft", "unknown")
    assert err is not None
    assert "must be one of" in err


def test_validate_status_transition_blocks_archived_update():
    err = validate_status_transition("archived", "active")
    assert err is not None
    assert "Archived" in err


def test_collect_course_ids_across_semesters_collects_planned_and_maybe():
    semesters = [
        {
            "plannedCourses": [{"courseId": "id1"}, {"courseId": "id2"}],
            "maybeCourses": [{"courseId": "id3"}],
        }
    ]
    ids = collect_course_ids_across_semesters(semesters)
    assert set(ids) == {"id1", "id2", "id3"}


def test_collect_course_ids_handles_empty_semesters():
    assert collect_course_ids_across_semesters([]) == []


def test_collect_course_ids_handles_missing_lists():
    semesters = [{"plannedCourses": None}]
    assert collect_course_ids_across_semesters(semesters) == []


# ---------------------------------------------------------------------------
# build_manual_planned_course
# ---------------------------------------------------------------------------

def test_build_manual_planned_course_returns_expected_shape():
    oid = ObjectId()
    course = {
        "_id": oid,
        "courseNumber": "00940101",
        "titleHebrew": "אלגברה",
        "credits": 4.0,
    }
    result = build_manual_planned_course(course)
    assert result["courseId"] == str(oid)
    assert result["courseNumber"] == "00940101"
    assert result["courseTitle"] == "אלגברה"
    assert result["credits"] == 4.0
    assert result["category"] == "manual"
    assert result["isActive"] is True
    assert result["selectedLessonEvents"] == []


def test_build_manual_planned_course_accepts_overrides():
    oid = ObjectId()
    course = {"_id": oid, "courseNumber": "123", "credits": 3}
    result = build_manual_planned_course(
        course,
        category="elective",
        reason="Student choice",
        is_active=False,
        notes="optional",
    )
    assert result["category"] == "elective"
    assert result["reason"] == "Student choice"
    assert result["isActive"] is False
    assert result["notes"] == "optional"


def test_build_manual_planned_course_uses_number_fallback():
    oid = ObjectId()
    course = {"_id": oid, "number": "00940999", "credits": 2}
    result = build_manual_planned_course(course)
    assert result["courseNumber"] == "00940999"


# ---------------------------------------------------------------------------
# build_manual_plan_document
# ---------------------------------------------------------------------------

def test_build_manual_plan_document_counts_active_courses():
    oid = ObjectId()
    semesters = [
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                {"courseId": str(oid), "credits": 4, "isActive": True},
                {"courseId": str(ObjectId()), "credits": 3, "isActive": False},
            ],
        }
    ]
    doc = build_manual_plan_document(name="My Plan", semesters=semesters)
    assert doc["name"] == "My Plan"
    assert doc["status"] == "draft"
    assert doc["plannerType"] == "manual"
    assert doc["explanation"]["emptyPlan"] is False
    assert doc["explanation"]["totalRecommendedCredits"] == 4.0


def test_build_manual_plan_document_marks_empty_plan():
    semesters = [{"semesterCode": "2025-2", "plannedCourses": []}]
    doc = build_manual_plan_document(name="Empty", semesters=semesters)
    assert doc["explanation"]["emptyPlan"] is True


def test_build_manual_plan_document_accepts_custom_status():
    semesters = [{"semesterCode": "2025-2", "plannedCourses": []}]
    doc = build_manual_plan_document(name="Active Plan", semesters=semesters, status="active")
    assert doc["status"] == "active"


# ---------------------------------------------------------------------------
# Async flows using mocks
# ---------------------------------------------------------------------------

def _make_mock_db(plan_doc=None, profile_doc=None, catalog_courses=None):
    """Build a lightweight mock DB for service-layer tests."""
    db = MagicMock()
    return db


@pytest.mark.asyncio
async def test_load_manual_plan_context_returns_profile_not_found():
    from app.services.manual_semester_plan_service import load_manual_plan_context

    db = MagicMock()
    with patch(
        "app.repositories.student_profile_repository.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await load_manual_plan_context(db, "user123")
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_load_manual_plan_context_returns_ok_with_profile():
    from app.services.manual_semester_plan_service import load_manual_plan_context

    profile = {"_id": ObjectId(), "userId": ObjectId()}
    db = MagicMock()
    with patch(
        "app.repositories.student_profile_repository.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        result = await load_manual_plan_context(db, "user123")
    assert result["status"] == "ok"
    assert result["profile"] == profile


@pytest.mark.asyncio
async def test_create_manual_semester_plan_returns_profile_not_found():
    from app.services.manual_semester_plan_service import create_manual_semester_plan

    db = MagicMock()
    with patch(
        "app.repositories.student_profile_repository.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await create_manual_semester_plan(db, "user123", {"name": "x", "semesterCode": "2025-2", "plannedCourses": []})
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_create_manual_semester_plan_returns_validation_error_for_empty_courses():
    from app.services.manual_semester_plan_service import create_manual_semester_plan

    profile = {"_id": ObjectId(), "userId": ObjectId()}
    db = MagicMock()
    with patch(
        "app.repositories.student_profile_repository.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await create_manual_semester_plan(
            db,
            "user123",
            {
                "name": "My Plan",
                "semesterCode": "2025-2",
                "plannedCourses": [],
            },
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_create_manual_semester_plan_returns_validation_error_for_unknown_course():
    from app.services.manual_semester_plan_service import create_manual_semester_plan

    profile = {"_id": ObjectId(), "userId": ObjectId()}
    db = MagicMock()
    with patch(
        "app.repositories.student_profile_repository.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await create_manual_semester_plan(
            db,
            "user123",
            {
                "name": "My Plan",
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseId": str(ObjectId())}],
            },
        )
    assert result["status"] == "validation_error"
    assert any("Unknown catalog courseId" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_returns_not_found():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await update_semester_plan_by_user(db, "user1", str(ObjectId()), {"name": "x"})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_returns_archived():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "archived", "explanation": {}, "version": 1}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await update_semester_plan_by_user(db, "user1", str(ObjectId()), {"name": "x"})
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_returns_validation_error_for_no_fields():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "draft", "explanation": {}, "version": 1}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await update_semester_plan_by_user(db, "user1", str(ObjectId()), {})
    assert result["status"] == "validation_error"
    assert any("No updatable fields" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_updates_name():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan_id = ObjectId()
    plan = {"_id": plan_id, "status": "draft", "explanation": {"summary": "x"}, "version": 1}
    updated_plan = {**plan, "name": "New Name", "version": 2}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated_plan,
    ):
        result = await update_semester_plan_by_user(
            db, "user1", str(plan_id), {"name": "New Name"}
        )
    assert result["status"] == "ok"
    assert result["plan"]["name"] == "New Name"


@pytest.mark.asyncio
async def test_create_semester_plan_version_by_user_returns_not_found():
    from app.services.manual_semester_plan_service import create_semester_plan_version_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await create_semester_plan_version_by_user(db, "user1", str(ObjectId()))
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_create_semester_plan_version_by_user_returns_archived_source():
    from app.services.manual_semester_plan_service import create_semester_plan_version_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await create_semester_plan_version_by_user(db, "user1", str(plan["_id"]))
    assert result["status"] == "archived_source"


@pytest.mark.asyncio
async def test_archive_semester_plan_by_user_returns_not_found():
    from app.services.manual_semester_plan_service import archive_semester_plan_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await archive_semester_plan_by_user(db, "user1", str(ObjectId()))
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_archive_semester_plan_by_user_is_idempotent_when_already_archived():
    from app.services.manual_semester_plan_service import archive_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await archive_semester_plan_by_user(db, "user1", str(plan["_id"]))
    assert result["status"] == "ok"
    assert result["plan"] == plan


@pytest.mark.asyncio
async def test_archive_semester_plan_by_user_archives_draft():
    from app.services.manual_semester_plan_service import archive_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "draft"}
    archived = {"_id": plan["_id"], "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=archived,
    ):
        result = await archive_semester_plan_by_user(db, "user1", str(plan["_id"]))
    assert result["status"] == "ok"
    assert result["plan"]["status"] == "archived"


@pytest.mark.asyncio
async def test_update_semester_plan_share_by_user_not_found():
    from app.services.manual_semester_plan_service import update_semester_plan_share_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await update_semester_plan_share_by_user(
            db, "user1", str(ObjectId()), share_enabled=True
        )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_update_semester_plan_share_by_user_archived():
    from app.services.manual_semester_plan_service import update_semester_plan_share_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await update_semester_plan_share_by_user(
            db, "user1", str(plan["_id"]), share_enabled=True
        )
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_update_semester_plan_share_generates_share_token():
    from app.services.manual_semester_plan_service import update_semester_plan_share_by_user

    plan = {"_id": ObjectId(), "status": "draft", "shareEnabled": False}
    updated = {**plan, "shareEnabled": True, "shareToken": "abc123"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated,
    ):
        result = await update_semester_plan_share_by_user(
            db, "user1", str(plan["_id"]), share_enabled=True
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_get_shared_semester_plan_by_token_not_found():
    from app.services.manual_semester_plan_service import get_shared_semester_plan_by_token

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_share_token",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await get_shared_semester_plan_by_token(db, "unknown-token")
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_shared_semester_plan_by_token_returns_not_found_for_archived():
    from app.services.manual_semester_plan_service import get_shared_semester_plan_by_token

    plan = {"_id": ObjectId(), "status": "archived", "shareEnabled": True}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_share_token",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await get_shared_semester_plan_by_token(db, "some-token")
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_shared_semester_plan_by_token_returns_ok():
    from app.services.manual_semester_plan_service import get_shared_semester_plan_by_token

    plan = {"_id": ObjectId(), "status": "active", "shareEnabled": True}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_share_token",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await get_shared_semester_plan_by_token(db, "valid-token")
    assert result["status"] == "ok"
    assert result["plan"] == plan


@pytest.mark.asyncio
async def test_patch_planned_course_by_user_returns_not_found():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_planned_course_by_user(db, "user1", str(ObjectId()), "00940101", {})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_patch_planned_course_by_user_returns_archived():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    plan = {"_id": ObjectId(), "status": "archived", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_planned_course_by_user(db, "user1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_patch_planned_course_by_user_returns_error_for_no_semesters():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    plan = {"_id": ObjectId(), "status": "draft", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_planned_course_by_user(db, "user1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("no semesters" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_planned_course_by_user_returns_error_for_missing_course():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    oid = ObjectId()
    plan = {
        "_id": oid,
        "status": "draft",
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}],
            }
        ],
        "explanation": {},
        "version": 1,
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_planned_course_by_user(db, "user1", str(oid), "99999999", {})
    assert result["status"] == "validation_error"
    assert any("99999999" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_reorder_planned_courses_by_user_returns_not_found():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await reorder_planned_courses_by_user(db, "user1", str(ObjectId()), ["id1"])
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_reorder_planned_courses_returns_validation_error_for_duplicates():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    plan = {
        "_id": ObjectId(),
        "status": "draft",
        "semesters": [
            {"plannedCourses": [{"courseId": "id1"}, {"courseId": "id2"}]}
        ],
        "version": 1,
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await reorder_planned_courses_by_user(db, "user1", str(plan["_id"]), ["id1", "id1"])
    assert result["status"] == "validation_error"
    assert any("Duplicate" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_create_manual_semester_plan_happy_path(mongo_database):
    """Full happy-path using mongomock for DB and mocking catalog."""
    from app.services.manual_semester_plan_service import create_manual_semester_plan
    from app.repositories.student_profile_repository import create_student_profile

    user_id = str(ObjectId())
    course_id = ObjectId()

    # Create a real profile in mongomock
    await create_student_profile(mongo_database, user_id, {
        "institutionId": "technion",
        "programType": "BSc",
        "catalogYear": 2024,
        "currentSemesterCode": "2024-2",
    })

    catalog_course = {
        "_id": course_id,
        "courseNumber": "00940101",
        "titleHebrew": "Algebra",
        "credits": 4.0,
    }

    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ), patch(
        "app.repositories.semester_plan_repository.create_semester_plan",
        new_callable=AsyncMock,
        return_value={"_id": ObjectId(), "name": "Test Plan", "status": "draft"},
    ):
        result = await create_manual_semester_plan(
            mongo_database,
            user_id,
            {
                "name": "Test Plan",
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseId": str(course_id)}],
            },
        )
    assert result["status"] == "ok"
    assert result["plan"]["name"] == "Test Plan"


@pytest.mark.asyncio
async def test_create_manual_semester_plan_duplicate_course_in_planned_and_maybe(mongo_database):
    """Test overlap between plannedCourses and maybeCourses is rejected."""
    from app.services.manual_semester_plan_service import create_manual_semester_plan
    from app.repositories.student_profile_repository import create_student_profile

    user_id = str(ObjectId())
    course_id = ObjectId()

    await create_student_profile(mongo_database, user_id, {
        "institutionId": "technion",
        "programType": "BSc",
        "catalogYear": 2024,
        "currentSemesterCode": "2024-2",
    })

    catalog_course = {
        "_id": course_id,
        "courseNumber": "00940101",
        "titleHebrew": "Algebra",
        "credits": 4.0,
    }

    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ):
        result = await create_manual_semester_plan(
            mongo_database,
            user_id,
            {
                "name": "Test Plan",
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseId": str(course_id)}],
                "maybeCourses": [{"courseId": str(course_id)}],  # same course!
            },
        )
    assert result["status"] == "validation_error"
    assert any("cannot appear in both" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_reorder_planned_courses_returns_validation_error_for_wrong_set():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    plan = {
        "_id": ObjectId(),
        "status": "draft",
        "semesters": [
            {"plannedCourses": [{"courseId": "id1"}, {"courseId": "id2"}]}
        ],
        "version": 1,
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await reorder_planned_courses_by_user(
            db, "user1", str(plan["_id"]), ["id1", "id3"]
        )
    assert result["status"] == "validation_error"


# ---------------------------------------------------------------------------
# _default_selected_groups / _selected_groups_from_input / _selected_lesson_events_from_input
# ---------------------------------------------------------------------------

def test_default_selected_groups_returns_empty_group_dict():
    from app.services.manual_semester_plan_service import _default_selected_groups

    groups = _default_selected_groups()
    assert groups == {"lecture": [], "tutorial": [], "lab": [], "project": []}


def test_selected_groups_from_input_calls_model_dump():
    from app.services.manual_semester_plan_service import _selected_groups_from_input

    class FakeGroups:
        def model_dump(self):
            return {"lecture": ["G1"], "tutorial": [], "lab": [], "project": []}

    item = {"selectedGroups": FakeGroups()}
    result = _selected_groups_from_input(item)
    assert result == {"lecture": ["G1"], "tutorial": [], "lab": [], "project": []}


def test_selected_groups_from_input_returns_none_when_missing():
    from app.services.manual_semester_plan_service import _selected_groups_from_input

    assert _selected_groups_from_input({}) is None


def test_selected_groups_from_input_converts_plain_dict():
    from app.services.manual_semester_plan_service import _selected_groups_from_input

    item = {"selectedGroups": {"lecture": ["G2"]}}
    result = _selected_groups_from_input(item)
    assert result == {"lecture": ["G2"]}


def test_selected_lesson_events_from_input_calls_model_dump():
    from app.services.manual_semester_plan_service import _selected_lesson_events_from_input

    class FakeEvent:
        def model_dump(self):
            return {"eventType": "lecture", "groupNumber": "1"}

    item = {"selectedLessonEvents": [FakeEvent()]}
    result = _selected_lesson_events_from_input(item)
    assert result == [{"eventType": "lecture", "groupNumber": "1"}]


def test_selected_lesson_events_from_input_converts_plain_dicts():
    from app.services.manual_semester_plan_service import _selected_lesson_events_from_input

    item = {"selectedLessonEvents": [{"eventType": "lab"}]}
    result = _selected_lesson_events_from_input(item)
    assert result == [{"eventType": "lab"}]


def test_selected_lesson_events_from_input_returns_none_when_missing():
    from app.services.manual_semester_plan_service import _selected_lesson_events_from_input

    assert _selected_lesson_events_from_input({}) is None


# ---------------------------------------------------------------------------
# _find_offering_match
# ---------------------------------------------------------------------------

def test_find_offering_match_returns_best_offering():
    from app.services.manual_semester_plan_service import _find_offering_match

    offerings = [
        {"courseNumber": "00940101", "academicYear": 2025, "semesterCode": 201},
        {"courseNumber": "00940101", "academicYear": 2024, "semesterCode": 201},
    ]
    result = _find_offering_match(offerings, academic_year=2025, semester_code=201)
    assert result is not None
    assert result["academicYear"] == 2025


# ---------------------------------------------------------------------------
# resolve_weekly_schedule_entries — uncovered branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_error_for_unknown_course_id():
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": True,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [{"courseId": "unknown_course", "academicYear": 2025, "semesterCode": 201}]
    entries, errors = await resolve_weekly_schedule_entries(
        db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
    )
    assert any("unknown_course" in e for e in errors)
    assert entries == []


@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_skips_inactive_course():
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": False,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [{"courseId": "course1", "academicYear": 2025, "semesterCode": 201}]
    entries, errors = await resolve_weekly_schedule_entries(
        db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
    )
    assert entries == []
    assert errors == []


@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_skips_when_schedule_groups_provided():
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": True,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [
        {
            "courseId": "course1",
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [{"day": "Sunday", "time": "10:00-12:00", "type": "lecture"}],
        }
    ]
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        entries, errors = await resolve_weekly_schedule_entries(
            db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
        )
    assert entries == []
    assert errors == []


@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_error_when_no_offering_found():
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": True,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [{"courseId": "course1", "academicYear": 2025, "semesterCode": 201}]
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        entries, errors = await resolve_weekly_schedule_entries(
            db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
        )
    assert any("No published offering" in e for e in errors)


@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_error_when_offering_has_no_schedule_groups():
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": True,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [{"courseId": "course1", "academicYear": 2025, "semesterCode": 201}]
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ):
        entries, errors = await resolve_weekly_schedule_entries(
            db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
        )
    assert any("no scheduleGroups" in e for e in errors)


@pytest.mark.asyncio
async def test_resolve_weekly_schedule_entries_second_loop_skips_unknown_course():
    """Second loop (built_entries) also checks planned_by_id — test missing course path."""
    from app.services.manual_semester_plan_service import resolve_weekly_schedule_entries

    db = MagicMock()
    # First entry is valid (so the first loop doesn't skip), but we manipulate state
    # to ensure the second loop handles the case where course_id is not in planned_by_id.
    # We use two entries: one valid for the first loop, one unknown in both loops.
    planned_courses = [
        {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X", "isActive": True,
         "selectedGroups": None, "selectedLessonEvents": []}
    ]
    schedule_inputs = [
        {"courseId": "course1", "academicYear": 2025, "semesterCode": 201},
        {"courseId": "course_unknown_2", "academicYear": 2025, "semesterCode": 201},
    ]
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        entries, errors = await resolve_weekly_schedule_entries(
            db, planned_courses=planned_courses, schedule_inputs=schedule_inputs
        )
    # course_unknown_2 generates error in both first and second loops
    assert sum(1 for e in errors if "course_unknown_2" in e) >= 1


# ---------------------------------------------------------------------------
# _build_planned_course_list_from_inputs — duplicate courseId
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_planned_course_list_from_inputs_duplicate_course_id():
    from app.services.manual_semester_plan_service import _build_planned_course_list_from_inputs

    oid = str(ObjectId())
    db = MagicMock()
    result, errors = await _build_planned_course_list_from_inputs(
        db,
        [{"courseId": oid}, {"courseId": oid}],
        field_label="plannedCourses",
    )
    assert result is None
    assert any("Duplicate" in e for e in errors)


# ---------------------------------------------------------------------------
# build_manual_semester_payload — maybeCourses errors & customEvents & schedule errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_manual_semester_payload_returns_error_for_maybe_courses_failure():
    from app.services.manual_semester_plan_service import build_manual_semester_payload

    course_id = ObjectId()
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 4.0, "titleHebrew": "X"}
    unknown_id = str(ObjectId())

    db = MagicMock()
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        side_effect=[
            [catalog_course],  # for planned
            [],               # for maybe -> triggers unknown course error
        ],
    ):
        payload, errors = await build_manual_semester_payload(
            db,
            semester_code="2025-2",
            goal_credits=None,
            order=1,
            notes=None,
            planned_course_inputs=[{"courseId": str(course_id)}],
            maybe_course_inputs=[{"courseId": unknown_id}],
            weekly_schedule_input=None,
        )
    assert payload is None
    assert any("Unknown catalog courseId" in e for e in errors)


@pytest.mark.asyncio
async def test_build_manual_semester_payload_includes_custom_events():
    from app.services.manual_semester_plan_service import build_manual_semester_payload

    course_id = ObjectId()
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 3.0, "titleHebrew": "Y"}

    db = MagicMock()
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ):
        custom_event = {"day": "Sunday", "startTime": "10:00", "endTime": "11:00", "title": "Study"}
        payload, errors = await build_manual_semester_payload(
            db,
            semester_code="2025-2",
            goal_credits=None,
            order=1,
            notes=None,
            planned_course_inputs=[{"courseId": str(course_id)}],
            weekly_schedule_input=None,
            custom_events=[custom_event],
        )
    assert errors == []
    assert payload is not None
    assert "customEvents" in payload
    assert len(payload["customEvents"]) == 1


@pytest.mark.asyncio
async def test_build_manual_semester_payload_returns_error_on_schedule_errors():
    from app.services.manual_semester_plan_service import build_manual_semester_payload

    course_id = ObjectId()
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 3.0, "titleHebrew": "Y"}

    db = MagicMock()
    weekly_schedule_input = {
        "entries": [
            {"courseId": str(course_id), "academicYear": 2025, "semesterCode": 201}
        ]
    }
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},  # no offering -> triggers schedule error
    ):
        payload, errors = await build_manual_semester_payload(
            db,
            semester_code="2025-2",
            goal_credits=None,
            order=1,
            notes=None,
            planned_course_inputs=[{"courseId": str(course_id)}],
            weekly_schedule_input=weekly_schedule_input,
        )
    assert payload is None
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# _build_semesters_from_request — cross-semester duplicate courseId
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_semesters_same_course_id_in_two_semesters():
    from app.services.manual_semester_plan_service import _build_semesters_from_request

    course_id = ObjectId()
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 3.0, "titleHebrew": "Z"}

    db = MagicMock()
    semesters_payload = [
        {
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": str(course_id)}],
            "maybeCourses": [],
        },
        {
            "semesterCode": "2026-1",
            "plannedCourses": [{"courseId": str(course_id)}],
            "maybeCourses": [],
        },
    ]
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ):
        semesters, errors = await _build_semesters_from_request(
            db,
            semesters_payload=semesters_payload,
            single_semester_payload=None,
        )
    assert semesters is None
    assert any("cannot appear in more than one semester" in e for e in errors)


# ---------------------------------------------------------------------------
# update_semester_plan_by_user — status transition error, status update, update None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_semester_plan_by_user_status_transition_error():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "draft", "explanation": {}, "version": 1}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await update_semester_plan_by_user(
            db, "user1", str(plan["_id"]), {"status": "invalid_status"}
        )
    assert result["status"] == "validation_error"
    assert any("must be one of" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_updates_status():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan_id = ObjectId()
    plan = {"_id": plan_id, "status": "draft", "explanation": {"summary": "old"}, "version": 1}
    updated = {**plan, "status": "active", "version": 2}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated,
    ):
        result = await update_semester_plan_by_user(
            db, "user1", str(plan_id), {"status": "active"}
        )
    assert result["status"] == "ok"
    assert result["plan"]["status"] == "active"


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_returns_not_found_when_update_returns_none():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan_id = ObjectId()
    plan = {"_id": plan_id, "status": "draft", "explanation": {}, "version": 1}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await update_semester_plan_by_user(
            db, "user1", str(plan_id), {"name": "New"}
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# _rebuild_weekly_schedule_for_semester
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rebuild_weekly_schedule_invalid_semester_code_returns_empty():
    from app.services.manual_semester_plan_service import _rebuild_weekly_schedule_for_semester

    db = MagicMock()
    semester = {"semesterCode": "INVALID", "plannedCourses": [], "customEvents": []}
    result, errors = await _rebuild_weekly_schedule_for_semester(db, semester)
    assert errors == []
    assert result is not None
    assert result["status"] == "empty"


@pytest.mark.asyncio
async def test_rebuild_weekly_schedule_returns_error_when_schedule_fails():
    from app.services.manual_semester_plan_service import _rebuild_weekly_schedule_for_semester

    db = MagicMock()
    semester = {
        "semesterCode": "2025-2",
        "plannedCourses": [
            {"courseId": "course1", "courseNumber": "00940101", "courseTitle": "X",
             "isActive": True, "selectedGroups": None, "selectedLessonEvents": []}
        ],
        "customEvents": [],
    }
    with patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result, errors = await _rebuild_weekly_schedule_for_semester(db, semester)
    assert result is None
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# patch_planned_course_by_user — selectedGroups, selectedLessonEvents, notes, schedule error, update None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_planned_course_updates_selected_groups():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    course_id = str(ObjectId())
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "status": "draft",
        "explanation": {},
        "version": 1,
        "semesters": [
            {
                "semesterCode": "INVALID",
                "plannedCourses": [
                    {"courseNumber": "00940101", "courseId": course_id, "credits": 3,
                     "isActive": True}
                ],
            }
        ],
    }
    updated_plan = {**plan, "version": 2}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated_plan,
    ):
        result = await patch_planned_course_by_user(
            db, "user1", str(plan_id), "00940101",
            {"selectedGroups": {"lecture": ["G1"], "tutorial": [], "lab": [], "project": []}}
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_patch_planned_course_updates_selected_lesson_events():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    course_id = str(ObjectId())
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "status": "draft",
        "explanation": {},
        "version": 1,
        "semesters": [
            {
                "semesterCode": "INVALID",
                "plannedCourses": [
                    {"courseNumber": "00940101", "courseId": course_id, "credits": 3,
                     "isActive": True}
                ],
            }
        ],
    }
    updated_plan = {**plan, "version": 2}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated_plan,
    ):
        result = await patch_planned_course_by_user(
            db, "user1", str(plan_id), "00940101",
            {"selectedLessonEvents": [{"eventType": "lecture", "groupNumber": "1"}]}
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_patch_planned_course_updates_notes():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    course_id = str(ObjectId())
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "status": "draft",
        "explanation": {},
        "version": 1,
        "semesters": [
            {
                "semesterCode": "INVALID",
                "plannedCourses": [
                    {"courseNumber": "00940101", "courseId": course_id, "credits": 3,
                     "isActive": True}
                ],
            }
        ],
    }
    updated_plan = {**plan, "version": 2}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated_plan,
    ):
        result = await patch_planned_course_by_user(
            db, "user1", str(plan_id), "00940101",
            {"notes": "Study extra hard"}
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_patch_planned_course_returns_validation_error_on_schedule_failure():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    course_id = str(ObjectId())
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "status": "draft",
        "explanation": {},
        "version": 1,
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [
                    {"courseNumber": "00940101", "courseId": course_id, "credits": 3,
                     "isActive": True}
                ],
            }
        ],
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await patch_planned_course_by_user(
            db, "user1", str(plan_id), "00940101",
            {"isActive": True}
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_planned_course_returns_not_found_when_update_returns_none():
    from app.services.manual_semester_plan_service import patch_planned_course_by_user

    course_id = str(ObjectId())
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "status": "draft",
        "explanation": {},
        "version": 1,
        "semesters": [
            {
                "semesterCode": "INVALID",
                "plannedCourses": [
                    {"courseNumber": "00940101", "courseId": course_id, "credits": 3,
                     "isActive": True}
                ],
            }
        ],
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_planned_course_by_user(
            db, "user1", str(plan_id), "00940101",
            {"isActive": False}
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# patch_lesson_selection_by_user — all missing branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_not_found():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(ObjectId()), "00940101", {})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_archived():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_error_no_semesters():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {"_id": ObjectId(), "status": "draft", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("no semesters" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_error_course_not_in_plan():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(plan["_id"]), "99999999", {})
    assert result["status"] == "validation_error"
    assert any("99999999" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_error_invalid_semester_code():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "INVALID", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("Invalid semester code" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_error_no_offering():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await patch_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("No published offering" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_validation_error_for_bad_events():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}]
    }
    offering = {
        "courseNumber": "00940101",
        "scheduleGroups": [{"day": "Sunday", "time": "10:00-12:00", "type": "lecture", "group": "1"}],
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=["Invalid lesson selection"],
    ):
        result = await patch_lesson_selection_by_user(
            db, "u1", str(plan["_id"]), "00940101",
            {"selectedLessonEvents": [{"eventType": "lab", "groupNumber": "99"}]}
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_lesson_selection_schedule_error_returns_validation_error():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}]
    }
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=[],
    ), patch(
        "app.services.manual_semester_plan_service._rebuild_weekly_schedule_for_semester",
        new_callable=AsyncMock,
        return_value=(None, ["schedule error"]),
    ):
        result = await patch_lesson_selection_by_user(
            db, "u1", str(plan["_id"]), "00940101", {}
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_lesson_selection_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import patch_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3, "isActive": True}
        ]}],
        "explanation": {}, "version": 1
    }
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=[],
    ), patch(
        "app.services.manual_semester_plan_service._rebuild_weekly_schedule_for_semester",
        new_callable=AsyncMock,
        return_value=({"status": "empty", "entries": []}, []),
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_lesson_selection_by_user(
            db, "u1", str(plan["_id"]), "00940101", {}
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# reorder_planned_courses_by_user — archived, no semesters, update None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reorder_planned_courses_returns_archived():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await reorder_planned_courses_by_user(db, "u1", str(plan["_id"]), [])
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_reorder_planned_courses_returns_error_no_semesters():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    plan = {"_id": ObjectId(), "status": "draft", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await reorder_planned_courses_by_user(db, "u1", str(plan["_id"]), [])
    assert result["status"] == "validation_error"
    assert any("no semesters" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_reorder_planned_courses_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import reorder_planned_courses_by_user

    plan_id = ObjectId()
    plan = {
        "_id": plan_id, "status": "draft", "version": 1,
        "semesters": [{"plannedCourses": [{"courseId": "id1"}]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await reorder_planned_courses_by_user(db, "u1", str(plan_id), ["id1"])
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# patch_maybe_courses_by_user — all missing branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_not_found():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_maybe_courses_by_user(db, "u1", str(ObjectId()), {})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_archived():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_courses_by_user(db, "u1", str(plan["_id"]), {})
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_error_no_semesters():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    plan = {"_id": ObjectId(), "status": "draft", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_courses_by_user(db, "u1", str(plan["_id"]), {})
    assert result["status"] == "validation_error"
    assert any("no semesters" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_error_for_unknown_course():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": []}]
    }
    unknown_id = str(ObjectId())
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await patch_maybe_courses_by_user(
            db, "u1", str(plan["_id"]),
            {"maybeCourses": [{"courseId": unknown_id}]}
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_error_for_overlap_with_planned():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    course_id = ObjectId()
    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [
            {"semesterCode": "2025-2", "plannedCourses": [
                {"courseId": str(course_id), "courseNumber": "00940101"}
            ]}
        ]
    }
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 3.0, "titleHebrew": "A"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ):
        result = await patch_maybe_courses_by_user(
            db, "u1", str(plan["_id"]),
            {"maybeCourses": [{"courseId": str(course_id)}]}
        )
    assert result["status"] == "validation_error"
    assert any("cannot appear in both" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_courses_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import patch_maybe_courses_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "plannedCourses": []}],
        "version": 1,
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_maybe_courses_by_user(
            db, "u1", str(plan["_id"]), {"maybeCourses": []}
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# patch_maybe_lesson_selection_by_user — complete coverage of entire function
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_not_found():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(ObjectId()), "00940101", {})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_archived():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {"_id": ObjectId(), "status": "archived"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_error_no_semesters():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {"_id": ObjectId(), "status": "draft", "semesters": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("no semesters" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_error_course_not_in_maybe():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "maybeCourses": []}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("not in maybeCourses" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_error_invalid_semester_code():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "INVALID", "maybeCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3}
        ]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("Invalid semester code" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_error_no_offering():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "maybeCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3}
        ]}]
    }
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await patch_maybe_lesson_selection_by_user(db, "u1", str(plan["_id"]), "00940101", {})
    assert result["status"] == "validation_error"
    assert any("No published offering" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_validation_error_for_bad_events():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "maybeCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3}
        ]}]
    }
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=["Invalid lesson type"],
    ):
        result = await patch_maybe_lesson_selection_by_user(
            db, "u1", str(plan["_id"]), "00940101",
            {"selectedLessonEvents": [{"eventType": "lab"}]}
        )
    assert result["status"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_happy_path_updates_and_returns_ok():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan_id = ObjectId()
    plan = {
        "_id": plan_id, "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "maybeCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3}
        ]}],
        "explanation": {}, "version": 1,
    }
    updated = {**plan, "version": 2}
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=[],
    ), patch(
        "app.services.manual_semester_plan_service._rebuild_weekly_schedule_for_semester",
        new_callable=AsyncMock,
        return_value=({"status": "empty"}, []),
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated,
    ):
        result = await patch_maybe_lesson_selection_by_user(
            db, "u1", str(plan_id), "00940101", {}
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_patch_maybe_lesson_selection_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import patch_maybe_lesson_selection_by_user

    plan_id = ObjectId()
    plan = {
        "_id": plan_id, "status": "draft",
        "semesters": [{"semesterCode": "2025-2", "maybeCourses": [
            {"courseNumber": "00940101", "courseId": str(ObjectId()), "credits": 3}
        ]}],
        "explanation": {}, "version": 1,
    }
    offering = {"courseNumber": "00940101", "scheduleGroups": []}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.list_best_offerings_for_courses",
        new_callable=AsyncMock,
        return_value={"00940101": offering},
    ), patch(
        "app.services.manual_semester_plan_service.validate_lesson_selection",
        return_value=[],
    ), patch(
        "app.services.manual_semester_plan_service._rebuild_weekly_schedule_for_semester",
        new_callable=AsyncMock,
        return_value=({"status": "empty"}, []),
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await patch_maybe_lesson_selection_by_user(
            db, "u1", str(plan_id), "00940101", {}
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# archive_semester_plan_by_user — update returns None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_archive_semester_plan_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import archive_semester_plan_by_user

    plan = {"_id": ObjectId(), "status": "draft"}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await archive_semester_plan_by_user(db, "u1", str(plan["_id"]))
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# update_semester_plan_share_by_user — update returns None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_semester_plan_share_returns_not_found_when_update_none():
    from app.services.manual_semester_plan_service import update_semester_plan_share_by_user

    plan = {"_id": ObjectId(), "status": "draft", "shareEnabled": False}
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await update_semester_plan_share_by_user(
            db, "u1", str(plan["_id"]), share_enabled=False
        )
    assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# update_semester_plan_by_user — semesters update path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_semester_plan_by_user_updates_semesters():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    course_id = ObjectId()
    plan_id = ObjectId()
    plan = {
        "_id": plan_id, "status": "draft",
        "explanation": {"summary": "old", "totalRecommendedCredits": 0},
        "version": 1,
    }
    catalog_course = {"_id": course_id, "courseNumber": "00940101", "credits": 3.0, "titleHebrew": "X"}
    updated = {**plan, "version": 2}
    db = MagicMock()
    semesters_payload = [
        {
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": str(course_id)}],
            "maybeCourses": [],
        }
    ]
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ), patch(
        "app.repositories.semester_plan_repository.update_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=updated,
    ):
        result = await update_semester_plan_by_user(
            db, "u1", str(plan_id), {"semesters": semesters_payload}
        )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_update_semester_plan_by_user_returns_validation_error_on_semesters_error():
    from app.services.manual_semester_plan_service import update_semester_plan_by_user

    plan = {
        "_id": ObjectId(), "status": "draft",
        "explanation": {}, "version": 1,
    }
    unknown_id = str(ObjectId())
    db = MagicMock()
    with patch(
        "app.repositories.semester_plan_repository.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.services.manual_semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await update_semester_plan_by_user(
            db, "u1", str(plan["_id"]),
            {"semesters": [{"semesterCode": "2025-2", "plannedCourses": [{"courseId": unknown_id}], "maybeCourses": []}]}
        )
    assert result["status"] == "validation_error"
