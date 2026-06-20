"""Unit tests for deterministic academic risk analyzer."""

from __future__ import annotations

from app.planning.academic_risk_analyzer import analyze_academic_risks
from tests.fixtures.semester_planner_fixtures import (
    ALGORITHMS,
    DATA_STRUCTURES,
    DISCRETE_MATH,
    FOUNDATIONS,
    MACHINE_LEARNING,
    build_completed_record,
    build_seed_like_context,
)


def _pool_documents() -> list[dict]:
    return [
        {
            "requirementGroupId": "CS-BSC:elective-pool",
            "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
            "courseReferences": [{"courseNumber": "02360363"}],
        }
    ]


def _build_analysis_context(*, completed_course_records=None):
    context = build_seed_like_context(completed_course_records=completed_course_records)
    context["poolDocuments"] = _pool_documents()

    remaining = [
        {
            "courseId": DISCRETE_MATH,
            "courseNumber": "02340102",
            "courseTitle": "Discrete Math",
        },
        {
            "courseId": DATA_STRUCTURES,
            "courseNumber": "02340201",
            "courseTitle": "Data Structures",
        },
        {
            "courseId": ALGORITHMS,
            "courseNumber": "02340301",
            "courseTitle": "Algorithms 1",
        },
    ]
    completed_ids = {
        str(record["courseId"])
        for record in (completed_course_records or [])
    }
    context["graduationProgress"] = {
        **context["graduationProgress"],
        "remainingMandatoryCourses": [
            course for course in remaining if course["courseId"] not in completed_ids
        ],
    }
    return context


def _planned_course(
    course_id: str,
    *,
    number: str,
    title: str,
    credits: float = 3.0,
    category: str = "mandatory",
) -> dict:
    return {
        "courseId": course_id,
        "courseNumber": number,
        "courseTitle": title,
        "credits": credits,
        "category": category,
        "reason": "Test planned course",
    }


def _analyze(context, plan_view):
    return analyze_academic_risks(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        pool_documents=context["poolDocuments"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        plan_view=plan_view,
    )


def test_detects_empty_plan_risk():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert analysis["summary"]["totalRisks"] >= 1
    assert any(risk["riskType"] == "empty_plan" for risk in analysis["risks"])
    assert analysis["summary"]["highestSeverity"] == "high"


def test_detects_credit_overload_and_too_few_credits():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
                _planned_course(DISCRETE_MATH, number="02340102", title="Discrete Math"),
                _planned_course(DATA_STRUCTURES, number="02340201", title="Data Structures"),
                _planned_course(ALGORITHMS, number="02340301", title="Algorithms 1"),
            ],
            "maxCredits": 9,
            "minCredits": 15,
            "explanation": {},
        },
    )

    assert any(risk["riskType"] == "credit_overload" for risk in analysis["risks"])
    assert any(risk["riskType"] == "too_few_credits" for risk in analysis["risks"])
    assert all(risk["source"] == "rule" for risk in analysis["risks"])


def test_detects_unmet_prerequisites_and_completed_course_risks():
    context = _build_analysis_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
                _planned_course(ALGORITHMS, number="02340301", title="Algorithms 1"),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert any(risk["riskType"] == "course_already_completed" for risk in analysis["risks"])
    assert any(risk["riskType"] == "unmet_prerequisites" for risk in analysis["risks"])
    prerequisite_risk = next(
        risk for risk in analysis["risks"] if risk["riskType"] == "unmet_prerequisites"
    )
    assert len(prerequisite_risk["evidence"]["missingPrerequisites"]) > 0
    assert len(prerequisite_risk["suggestedFixes"]) > 0


def test_detects_failed_course_retake_warning():
    context = _build_analysis_context(
        completed_course_records=[build_completed_record(FOUNDATIONS, grade=0, credits_earned=0)],
    )
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert any(risk["riskType"] == "failed_course_retake" for risk in analysis["risks"])


def test_detects_elective_only_plan_while_mandatory_requirements_remain():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(
                    MACHINE_LEARNING,
                    number="02360363",
                    title="Machine Learning",
                    category="elective",
                ),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert any(risk["riskType"] == "no_mandatory_progress" for risk in analysis["risks"])
    assert any(risk["riskType"] == "unmet_prerequisites" for risk in analysis["risks"])


def test_includes_partial_plan_risk_from_persisted_planner_explanation():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
            ],
            "maxCredits": 12,
            "minCredits": 9,
            "explanation": {
                "partialPlan": True,
                "summary": "Partial plan generated because workload limits prevented reaching minCredits",
            },
        },
    )

    assert any(risk["riskType"] == "partial_plan" for risk in analysis["risks"])


def test_detects_insufficient_graduation_progress():
    context = _build_analysis_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(
                    FOUNDATIONS,
                    number="02340101",
                    title="Foundations",
                    category="mandatory",
                ),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert any(
        risk["riskType"] == "insufficient_graduation_progress" for risk in analysis["risks"]
    )
    assert not any(risk["riskType"] == "no_mandatory_progress" for risk in analysis["risks"])


def test_detects_deferred_planner_warnings_from_explanation_evidence():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {
                "partialPlan": False,
                "blockedByPrerequisites": [
                    {
                        "courseId": DATA_STRUCTURES,
                        "courseNumber": "02340201",
                        "courseTitle": "Data Structures",
                    }
                ],
                "skippedDueToWorkload": [
                    {
                        "courseId": DISCRETE_MATH,
                        "courseNumber": "02340102",
                        "courseTitle": "Discrete Math",
                    }
                ],
            },
        },
    )

    assert any(
        risk["riskType"] == "deferred_prerequisite_blocked_courses" for risk in analysis["risks"]
    )
    assert any(
        risk["riskType"] == "deferred_workload_limited_courses" for risk in analysis["risks"]
    )
    assert analysis["contextSnapshot"]["plannedCourseIds"] == [FOUNDATIONS]


def test_detects_duplicate_planned_courses():
    context = _build_analysis_context()
    analysis = _analyze(
        context,
        {
            "semesterCode": "2025-2",
            "plannedCourses": [
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
                _planned_course(FOUNDATIONS, number="02340101", title="Foundations"),
            ],
            "maxCredits": 12,
            "minCredits": 0,
            "explanation": {},
        },
    )

    assert any(risk["riskType"] == "duplicate_planned_course" for risk in analysis["risks"])
