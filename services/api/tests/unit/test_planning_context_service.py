"""Unit tests for planning context envelope builder."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.services.planning_context_service import (
    _compact_graduation,
    _compact_risk_analysis,
    _compact_semester_plan,
    build_planning_context_envelope,
)


def test_compact_graduation_limits_missing_requirements():
    progress = {
        "degreeCode": "CS-BSC",
        "completedCredits": 90,
        "totalRequiredCredits": 120,
        "creditsRemaining": 30,
        "completionPercentage": 75,
        "statusSummary": "on_track",
        "missingRequirements": [{"title": f"Req {index}"} for index in range(8)],
        "remainingMandatoryCourses": [],
        "remainingElectiveCredits": 6,
    }
    compact = _compact_graduation(progress)
    assert compact["missingRequirementCount"] == 8
    assert len(compact["topMissingRequirements"]) == 5
    assert compact["completionPercentage"] == 75


def test_compact_semester_plan_extracts_course_numbers():
    plan = {
        "_id": ObjectId(),
        "name": "Spring plan",
        "status": "draft",
        "plannerType": "deterministic",
        "semesters": [
            {
                "semesterCode": "2025-201",
                "goalCredits": 18,
                "plannedCourses": [
                    {"courseNumber": "00440148"},
                    {"courseNumber": "00440213"},
                ],
            }
        ],
    }
    compact = _compact_semester_plan(plan)
    assert compact["semesterCode"] == "2025-201"
    assert compact["plannedCourseNumbers"] == ["00440148", "00440213"]


def test_compact_risk_analysis_top_risks():
    analysis = {
        "_id": ObjectId(),
        "semesterCode": "2025-201",
        "status": "open",
        "summary": {"highestSeverity": "high", "totalRisks": 2},
        "risks": [
            {"severity": "high", "title": "Overload", "riskType": "credit_overload"},
            {"severity": "medium", "title": "Prereq gap", "riskType": "prerequisite"},
        ],
    }
    compact = _compact_risk_analysis(analysis)
    assert compact["highestSeverity"] == "high"
    assert len(compact["topRisks"]) == 2


@pytest.mark.asyncio
async def test_build_planning_context_envelope_ok():
    database = AsyncMock()
    progress = {
        "degreeCode": "CS-BSC",
        "completedCredits": 60,
        "totalRequiredCredits": 120,
        "creditsRemaining": 60,
        "completionPercentage": 50,
        "missingRequirements": [],
        "remainingMandatoryCourses": [],
        "remainingElectiveCredits": 0,
        "statusSummary": "in_progress",
    }

    with (
        patch(
            "app.services.planning_context_service.get_graduation_progress_for_user",
            new=AsyncMock(return_value={"status": "ok", "progress": progress}),
        ),
        patch(
            "app.services.planning_context_service.find_semester_plans_by_user_id",
            new=AsyncMock(return_value={"plans": [], "total": 0}),
        ),
        patch(
            "app.services.planning_context_service.find_academic_risk_analyses_by_user_id",
            new=AsyncMock(return_value={"analyses": [], "total": 0}),
        ),
    ):
        envelope = await build_planning_context_envelope(database, str(ObjectId()))

    assert envelope["available"] is True
    assert envelope["graduation"]["completedCredits"] == 60
    assert envelope["latest_plan"] is None
    assert envelope["latest_risk"] is None


@pytest.mark.asyncio
async def test_build_planning_context_envelope_profile_not_found():
    database = AsyncMock()
    with patch(
        "app.services.planning_context_service.get_graduation_progress_for_user",
        new=AsyncMock(return_value={"status": "profile_not_found"}),
    ):
        envelope = await build_planning_context_envelope(database, str(ObjectId()))

    assert envelope["available"] is False
    assert envelope["status"] == "profile_not_found"
