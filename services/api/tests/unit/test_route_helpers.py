"""Unit tests for route helper functions — covers missed lines in routes/ modules."""

from __future__ import annotations

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# routes/semester_plans.py: _handle_planning_context_error, _handle_manual_plan_result
# ---------------------------------------------------------------------------

def test_handle_planning_context_error_degree_not_found():
    from app.routes.semester_plans import _handle_planning_context_error

    with pytest.raises(HTTPException) as exc_info:
        _handle_planning_context_error({"status": "degree_not_found"})
    assert exc_info.value.status_code == 400
    assert "degree" in exc_info.value.detail.lower()


def test_handle_planning_context_error_degree_not_selected():
    from app.routes.semester_plans import _handle_planning_context_error

    with pytest.raises(HTTPException) as exc_info:
        _handle_planning_context_error({"status": "degree_not_selected"})
    assert exc_info.value.status_code == 400


def test_handle_manual_plan_result_degree_not_selected():
    from app.routes.semester_plans import _handle_manual_plan_result

    with pytest.raises(HTTPException) as exc_info:
        _handle_manual_plan_result({"status": "degree_not_selected"})
    assert exc_info.value.status_code == 400


def test_handle_manual_plan_result_degree_not_found():
    from app.routes.semester_plans import _handle_manual_plan_result

    with pytest.raises(HTTPException) as exc_info:
        _handle_manual_plan_result({"status": "degree_not_found"})
    assert exc_info.value.status_code == 400


def test_handle_manual_plan_result_returns_result_for_ok():
    from app.routes.semester_plans import _handle_manual_plan_result

    result = {"status": "ok", "plan": {"_id": "x"}}
    returned = _handle_manual_plan_result(result)
    assert returned == result


def test_handle_manual_plan_result_profile_not_found():
    from app.routes.semester_plans import _handle_manual_plan_result

    with pytest.raises(HTTPException) as exc_info:
        _handle_manual_plan_result({"status": "profile_not_found"})
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# routes/academic_risks.py: _handle_risk_context_error — degree_not_found
# ---------------------------------------------------------------------------

def test_handle_analysis_context_error_degree_not_found():
    from app.routes.academic_risks import _handle_analysis_context_error

    with pytest.raises(HTTPException) as exc_info:
        _handle_analysis_context_error({"status": "degree_not_found"})
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# routes/student_profile.py: profile not found in update path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_profile_route_returns_404_when_update_returns_none(auth_client, mongo_database):
    from unittest.mock import AsyncMock, patch

    VALID_PASSWORD = "StrongPass123!"
    email = "profile-update-404@example.com"
    reg_resp = await auth_client.post("/auth/register", json={"email": email, "password": VALID_PASSWORD})
    assert reg_resp.status_code == 201
    token = reg_resp.json()["data"]["accessToken"]

    # Create profile so find_student_profile_by_user_id returns a result
    await auth_client.post(
        "/student-profile",
        json={"institutionId": "technion", "programType": "BSc", "catalogYear": 2024, "currentSemesterCode": "2024-2"},
        headers={"Authorization": f"Bearer {token}"},
    )

    with patch(
        "app.routes.student_profile.update_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await auth_client.put(
            "/student-profile",
            json={"catalogYear": 2025},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# services/graduation_requirement_links.py: bucket_suffix_from_group_id
# ---------------------------------------------------------------------------

def test_bucket_suffix_returns_group_id_when_no_program_prefix():
    from app.services.graduation_requirement_links import bucket_suffix_from_group_id

    result = bucket_suffix_from_group_id("some-other-group", "009216-1-000")
    assert result == "some-other-group"


def test_bucket_suffix_strips_program_prefix():
    from app.services.graduation_requirement_links import bucket_suffix_from_group_id

    result = bucket_suffix_from_group_id("009216-1-000:elective-ds", "009216-1-000")
    assert result == "elective-ds"


# ---------------------------------------------------------------------------
# services/planner_enrichment_service.py: _load_offerings_for_plan_semester
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_offerings_for_plan_semester_returns_empty_for_invalid_code():
    from unittest.mock import MagicMock

    from app.services.planner_enrichment_service import _offerings_for_planned_courses

    db = MagicMock()
    result = await _offerings_for_planned_courses(
        db,
        semester_code="INVALID",
        planned_courses=[{"courseNumber": "00940101"}],
    )
    assert result == {}


# ---------------------------------------------------------------------------
# services/semester_plan_service.py: _collect_planning_course_ids with courseId in remaining
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collect_planning_course_ids_includes_remaining_mandatory():
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId

    from app.services.semester_plan_service import _load_planning_catalog_courses as _collect_planning_courses

    course_id = str(ObjectId())
    graduation_progress = {
        "remainingMandatoryCourses": [{"courseId": course_id, "courseNumber": "00940101"}]
    }

    db = MagicMock()
    catalog_course = {"_id": ObjectId(course_id), "courseNumber": "00940101", "credits": 3.0, "status": "published"}
    with patch(
        "app.services.semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[catalog_course],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.find_courses_by_numbers",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.list_courses_by_number_prefixes",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await _collect_planning_courses(
            db,
            graduation_progress=graduation_progress,
            hard_requirements=[],
            pool_documents=[],
            semester_matrix_documents=[],
            completed_course_records=[],
        )
    assert any(str(c.get("_id")) == course_id for c in result)


# ---------------------------------------------------------------------------
# routes/semester_plans.py: _public_plan_with_insights returns {} when public is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_plan_with_insights_returns_empty_when_public_none():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.routes.semester_plans import _public_plan_with_insights

    db = MagicMock()
    plan = {"_id": "some-id", "status": "draft", "name": "Test"}

    with patch(
        "app.routes.semester_plans.resolve_public_plan_insights",
        new_callable=AsyncMock,
        return_value={"_id": None},  # return a plan with no _id → to_public_semester_plan returns None
    ), patch(
        "app.routes.semester_plans.to_public_semester_plan",
        return_value=None,
    ):
        result = await _public_plan_with_insights(db, "user1", plan)
    assert result == {}
