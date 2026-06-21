"""Unit tests for semester_plan_service and academic_risk_service orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

# ---------------------------------------------------------------------------
# semester_plan_service
# ---------------------------------------------------------------------------

from app.services.semester_plan_service import (
    _collect_planning_course_numbers,
    _pool_allowed_prefixes,
    _pool_course_numbers,
    _matrix_course_numbers,
)


def test_pool_course_numbers_extracts_numbers():
    pool = {
        "courseReferences": [
            {"courseNumber": "00940101"},
            {"courseNumber": "00940102"},
        ]
    }
    result = _pool_course_numbers(pool)
    assert result == {"00940101", "00940102"}


def test_pool_course_numbers_handles_empty():
    assert _pool_course_numbers({}) == set()
    assert _pool_course_numbers({"courseReferences": []}) == set()


def test_pool_allowed_prefixes_extracts_prefixes():
    pool = {"ruleExpression": {"allowedPrefixes": ["009", "234"]}}
    result = _pool_allowed_prefixes(pool)
    assert result == ["009", "234"]


def test_pool_allowed_prefixes_handles_empty():
    assert _pool_allowed_prefixes({}) == []
    assert _pool_allowed_prefixes({"ruleExpression": {}}) == []


def test_matrix_course_numbers_extracts_numbers():
    matrix_docs = [
        {"courseReferences": [{"courseNumber": "00940101"}]},
        {"courseReferences": [{"courseNumber": "00940102"}, {}]},
    ]
    result = _matrix_course_numbers(matrix_docs)
    assert "00940101" in result
    assert "00940102" in result


def test_collect_planning_course_numbers_aggregates_sources():
    graduation_progress = {
        "remainingMandatoryCourses": [{"courseNumber": "001"}, {}],
        "requirementProgress": [
            {"remainingCourses": [{"courseNumber": "002"}]}
        ],
    }
    hard_requirements = [
        {"courseReferences": [{"courseNumber": "003"}]}
    ]
    pool_documents = [
        {"courseReferences": [{"courseNumber": "004"}]}
    ]
    semester_matrix_documents = [
        {"courseReferences": [{"courseNumber": "005"}]}
    ]
    result = _collect_planning_course_numbers(
        graduation_progress=graduation_progress,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        semester_matrix_documents=semester_matrix_documents,
    )
    assert {"001", "002", "003", "004", "005"}.issubset(result)


@pytest.mark.asyncio
async def test_load_planning_context_returns_profile_not_found():
    from app.services.semester_plan_service import load_planning_context

    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await load_planning_context(db, "user123")
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_load_planning_context_returns_degree_not_selected():
    from app.services.semester_plan_service import load_planning_context

    profile = {"_id": ObjectId(), "degreeId": None}
    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        result = await load_planning_context(db, "user123")
    assert result["status"] == "degree_not_selected"


@pytest.mark.asyncio
async def test_load_planning_context_returns_degree_not_found():
    from app.services.semester_plan_service import load_planning_context

    profile = {"_id": ObjectId(), "degreeId": str(ObjectId())}
    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.semester_plan_service.catalog_repository.find_degree_program_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await load_planning_context(db, "user123")
    assert result["status"] == "degree_not_found"


@pytest.mark.asyncio
async def test_generate_and_store_semester_plan_propagates_context_errors():
    from app.services.semester_plan_service import generate_and_store_semester_plan

    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "profile_not_found"},
    ):
        result = await generate_and_store_semester_plan(db, "user1", {"semesterCode": "2025-2"})
    assert result["status"] == "profile_not_found"


# ---------------------------------------------------------------------------
# academic_risk_service
# ---------------------------------------------------------------------------

from app.services.academic_risk_service import build_plan_view_from_semester_plan


def test_build_plan_view_from_semester_plan_extracts_fields():
    plan_id = ObjectId()
    plan = {
        "_id": plan_id,
        "semesters": [
            {
                "semesterCode": "2025-2",
                "plannedCourses": [{"courseId": "c1"}],
                "constraintsSnapshot": {"maxCredits": 20},
            }
        ],
        "explanation": {"summary": "ok"},
        "plannerType": "manual",
    }
    result = build_plan_view_from_semester_plan(plan)
    assert result["planId"] == str(plan_id)
    assert result["semesterCode"] == "2025-2"
    assert len(result["plannedCourses"]) == 1
    assert result["maxCredits"] == 20
    assert result["plannerType"] == "manual"
    assert result["analysisSource"] == "semester_plan"


def test_build_plan_view_from_semester_plan_handles_empty_semesters():
    plan = {
        "_id": ObjectId(),
        "semesters": [],
        "explanation": {},
        "plannerType": "deterministic",
    }
    result = build_plan_view_from_semester_plan(plan)
    assert result["semesterCode"] is None
    assert result["plannedCourses"] == []


@pytest.mark.asyncio
async def test_analyze_and_store_academic_risks_propagates_context_errors():
    from app.services.academic_risk_service import analyze_and_store_academic_risks

    db = MagicMock()
    with patch(
        "app.services.academic_risk_service.load_planning_context",
        new_callable=AsyncMock,
        return_value={"status": "profile_not_found"},
    ):
        result = await analyze_and_store_academic_risks(
            db, "user1", {"semesterCode": "2025-2", "courseIds": []}
        )
    assert result["status"] == "profile_not_found"


@pytest.mark.asyncio
async def test_analyze_and_store_academic_risks_plan_not_found():
    from app.services.academic_risk_service import analyze_and_store_academic_risks

    context = {
        "status": "ok",
        "profile": {},
        "degree": {"institutionId": "tech", "catalogYear": 2024},
        "catalogCourses": [],
        "poolDocuments": [],
        "graduationProgress": {},
        "completedCourseRecords": [],
    }
    db = MagicMock()
    with patch(
        "app.services.academic_risk_service.load_planning_context",
        new_callable=AsyncMock,
        return_value=context,
    ), patch(
        "app.services.academic_risk_service.find_semester_plan_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await analyze_and_store_academic_risks(
            db, "user1", {"semesterCode": "2025-2", "planId": str(ObjectId())}
        )
    assert result["status"] == "plan_not_found"


@pytest.mark.asyncio
async def test_list_academic_risk_analyses_for_user_delegates_to_repo():
    from app.services.academic_risk_service import list_academic_risk_analyses_for_user

    db = MagicMock()
    expected = {"analyses": [], "total": 0, "page": 1, "limit": 50}
    with patch(
        "app.repositories.academic_risk_repository.find_academic_risk_analyses_by_user_id",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        result = await list_academic_risk_analyses_for_user(db, "user1", {"page": 1, "limit": 50})
    assert result == expected


@pytest.mark.asyncio
async def test_get_academic_risk_analysis_for_user_returns_not_found():
    from app.services.academic_risk_service import get_academic_risk_analysis_for_user

    db = MagicMock()
    with patch(
        "app.repositories.academic_risk_repository.find_academic_risk_analysis_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await get_academic_risk_analysis_for_user(db, "user1", str(ObjectId()))
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_academic_risk_analysis_for_user_returns_ok():
    from app.services.academic_risk_service import get_academic_risk_analysis_for_user

    analysis = {"_id": ObjectId(), "status": "open"}
    db = MagicMock()
    with patch(
        "app.repositories.academic_risk_repository.find_academic_risk_analysis_by_id_and_user_id",
        new_callable=AsyncMock,
        return_value=analysis,
    ):
        result = await get_academic_risk_analysis_for_user(db, "user1", str(analysis["_id"]))
    assert result["status"] == "ok"
    assert result["analysis"] == analysis


# ---------------------------------------------------------------------------
# build_plan_view_from_adhoc
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_plan_view_from_adhoc_handles_unknown_course():
    from app.services.academic_risk_service import build_plan_view_from_adhoc

    db = MagicMock()
    degree = {"institutionId": "technion", "catalogYear": 2024}
    course_id = str(ObjectId())
    with patch(
        "app.services.academic_risk_service.catalog_repository.find_course_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await build_plan_view_from_adhoc(
            db, degree, {"courseIds": [course_id], "semesterCode": "2025-2"}
        )
    assert len(result["plannedCourses"]) == 1
    assert result["plannedCourses"][0]["catalogScopeValid"] is True
    assert result["plannedCourses"][0]["credits"] == 0


@pytest.mark.asyncio
async def test_build_plan_view_from_adhoc_handles_in_scope_course():
    from app.services.academic_risk_service import build_plan_view_from_adhoc

    db = MagicMock()
    degree = {"institutionId": "technion", "catalogYear": 2024}
    course_id = str(ObjectId())
    catalog_course = {
        "_id": ObjectId(course_id),
        "courseNumber": "00940101",
        "titleHebrew": "Algebra",
        "credits": 4.0,
        "institutionId": "technion",
        "catalogYear": 2024,
    }
    with patch(
        "app.services.academic_risk_service.catalog_repository.find_course_by_id",
        new_callable=AsyncMock,
        return_value=catalog_course,
    ):
        result = await build_plan_view_from_adhoc(
            db, degree, {"courseIds": [course_id], "semesterCode": "2025-2"}
        )
    assert len(result["plannedCourses"]) == 1
    assert result["plannedCourses"][0]["catalogScopeValid"] is True
    assert result["plannedCourses"][0]["credits"] == 4.0


@pytest.mark.asyncio
async def test_build_plan_view_from_adhoc_handles_out_of_scope_course():
    from app.services.academic_risk_service import build_plan_view_from_adhoc

    db = MagicMock()
    degree = {"institutionId": "technion", "catalogYear": 2024}
    course_id = str(ObjectId())
    catalog_course = {
        "_id": ObjectId(course_id),
        "courseNumber": "00940101",
        "titleHebrew": "Algebra",
        "credits": 4.0,
        "institutionId": "other_institution",  # out of scope
        "catalogYear": 2024,
    }
    with patch(
        "app.services.academic_risk_service.catalog_repository.find_course_by_id",
        new_callable=AsyncMock,
        return_value=catalog_course,
    ):
        result = await build_plan_view_from_adhoc(
            db, degree, {"courseIds": [course_id], "semesterCode": "2025-2"}
        )
    assert len(result["plannedCourses"]) == 1
    assert result["plannedCourses"][0]["catalogScopeValid"] is False


# ---------------------------------------------------------------------------
# semester_plan_service - generate_and_store full path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_planning_context_full_ok_path():
    from app.services.semester_plan_service import load_planning_context

    degree_id = str(ObjectId())
    profile = {"_id": ObjectId(), "degreeId": degree_id}
    degree_program = {"_id": ObjectId(), "programCode": "009-1", "totalCreditsRequired": 180}
    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.find_student_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.services.semester_plan_service.catalog_repository.find_degree_program_by_id",
        new_callable=AsyncMock,
        return_value=degree_program,
    ), patch(
        "app.services.semester_plan_service.catalog_repository.list_hard_requirements_for_program",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.list_course_pools_for_program",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.list_semester_matrix_rules_for_program",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.find_all_completed_courses_by_user_id",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.find_courses_by_ids",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.find_courses_by_numbers",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.semester_plan_service.catalog_repository.list_courses_by_number_prefixes",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await load_planning_context(db, "user1")
    assert result["status"] == "ok"
    assert result["profile"] == profile
    assert result["degree"] == degree_program
    assert "graduationProgress" in result
    assert "catalogCourses" in result


@pytest.mark.asyncio
async def test_generate_and_store_semester_plan_ok_path():
    from app.services.semester_plan_service import generate_and_store_semester_plan

    stored = {"_id": ObjectId(), "name": "Generated Plan", "status": "draft"}
    context = {
        "status": "ok",
        "profile": {"currentSemesterCode": "2025-2"},
        "degree": {"_id": ObjectId(), "programCode": "test"},
        "catalogCourses": [],
        "graduationProgress": {},
        "completedCourseRecords": [],
        "hardRequirements": [],
        "poolDocuments": [],
        "semesterMatrixDocuments": [],
    }
    db = MagicMock()
    with patch(
        "app.services.semester_plan_service.load_planning_context",
        new_callable=AsyncMock,
        return_value=context,
    ), patch(
        "app.services.semester_plan_service.generate_deterministic_semester_plan",
        return_value={"name": "Generated Plan", "semesters": [], "explanation": {}},
    ), patch(
        "app.services.semester_plan_service.create_semester_plan",
        new_callable=AsyncMock,
        return_value=stored,
    ):
        result = await generate_and_store_semester_plan(
            db, "user1", {"semesterCode": "2025-2"}
        )
    assert result["status"] == "ok"
    assert result["plan"] == stored
