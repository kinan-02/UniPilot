"""Unit tests for proactive watchdog checks (AGT-8)."""

from __future__ import annotations

from bson import ObjectId

from app.services.watchdog_checks import (
    check_credits_behind_track,
    check_mandatory_courses_remaining,
    check_open_high_severity_risks,
    collect_watchdog_nudges,
    parse_plan_semester_code,
    program_semester_index,
)


def test_check_mandatory_courses_remaining_flags_open_requirements():
    profile = {"degreeId": "deg-1"}
    graduation_progress = {
        "remainingMandatoryCourses": [
            {"courseNumber": "02340101"},
            {"courseNumber": "02340102"},
        ],
    }

    nudge = check_mandatory_courses_remaining(
        profile=profile,
        graduation_progress=graduation_progress,
    )

    assert nudge is not None
    assert nudge.nudge_type == "pace"
    assert nudge.evidence["remainingMandatoryCount"] == 2


def test_parse_plan_semester_code_supports_technion_codes():
    assert parse_plan_semester_code("2025-201") == (2025, 2)
    assert parse_plan_semester_code("2025-2") == (2025, 2)


def test_program_semester_index_counts_terms_since_catalog_year():
    assert program_semester_index(2024, "2025-201") == 5


def test_check_credits_behind_track_flags_missing_matrix_courses():
    profile = {"catalogYear": 2024, "currentSemesterCode": "2026-201"}
    graduation_progress = {
        "completionPercentage": 20,
        "completedMandatoryCourses": [{"courseNumber": "02340101"}],
    }
    matrix = [
        {
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "02340101"}],
        },
        {
            "ruleExpression": {"type": "semester_matrix", "semester": 2},
            "courseReferences": [{"courseNumber": "02340102"}],
        },
        {
            "ruleExpression": {"type": "semester_matrix", "semester": 3},
            "courseReferences": [{"courseNumber": "02340201"}, {"courseNumber": "02340301"}],
        },
    ]

    nudge = check_credits_behind_track(
        profile=profile,
        graduation_progress=graduation_progress,
        semester_matrix_documents=matrix,
    )

    assert nudge is not None
    assert nudge.nudge_type == "pace"
    assert "02340102" in nudge.evidence["missingMandatoryCourseNumbers"]


def test_check_open_high_severity_risks_builds_nudge():
    analysis_id = ObjectId()
    nudge = check_open_high_severity_risks(
        {
            "_id": analysis_id,
            "status": "open",
            "summary": {"highestSeverity": "high", "totalRisks": 1},
            "risks": [
                {
                    "severity": "high",
                    "title": "Credit overload",
                    "explanation": "Plan exceeds recommended load.",
                    "riskType": "credit_overload",
                }
            ],
        }
    )

    assert nudge is not None
    assert nudge.nudge_type == "risk"
    assert nudge.dedupe_key == f"risk:{analysis_id}"


def test_collect_watchdog_nudges_includes_pace_and_risk():
    profile = {"catalogYear": 2024, "currentSemesterCode": "2026-201"}
    graduation_progress = {
        "completionPercentage": 10,
        "completedMandatoryCourses": [],
    }
    matrix = [
        {
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "02340101"}, {"courseNumber": "02340102"}],
        }
    ]
    risk_doc = {
        "_id": ObjectId(),
        "status": "open",
        "summary": {"highestSeverity": "high"},
        "risks": [{"severity": "high", "title": "Overload", "explanation": "Too many credits"}],
    }

    nudges = collect_watchdog_nudges(
        profile=profile,
        graduation_progress=graduation_progress,
        semester_matrix_documents=matrix,
        latest_plan=None,
        latest_risk_analysis=risk_doc,
        planning_context=None,
    )

    types = {nudge.nudge_type for nudge in nudges}
    assert "pace" in types
    assert "risk" in types
