"""Compact planning envelope for the AI advisor planning swarm (AGT-2)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.academic_risk_repository import find_academic_risk_analyses_by_user_id
from app.repositories.semester_plan_repository import find_semester_plans_by_user_id
from app.services.graduation_progress_service import get_graduation_progress_for_user


def _compact_graduation(progress: dict[str, Any]) -> dict[str, Any]:
    missing = progress.get("missingRequirements") or []
    top_missing = [
        {
            "title": item.get("title"),
            "status": item.get("status"),
            "creditsRemaining": item.get("creditsRemaining"),
        }
        for item in missing[:5]
        if isinstance(item, dict)
    ]
    return {
        "degreeCode": progress.get("degreeCode"),
        "degreeName": progress.get("degreeName"),
        "catalogYear": progress.get("catalogYear"),
        "completedCredits": progress.get("completedCredits"),
        "totalRequiredCredits": progress.get("totalRequiredCredits"),
        "creditsRemaining": progress.get("creditsRemaining"),
        "completionPercentage": progress.get("completionPercentage"),
        "statusSummary": progress.get("statusSummary"),
        "missingRequirementCount": len(missing),
        "topMissingRequirements": top_missing,
        "remainingMandatoryCourseCount": len(progress.get("remainingMandatoryCourses") or []),
        "remainingElectiveCredits": progress.get("remainingElectiveCredits"),
    }


def _course_numbers_from_planned_courses(planned_courses: list[dict[str, Any]]) -> list[str]:
    numbers: list[str] = []
    for course in planned_courses:
        if not isinstance(course, dict):
            continue
        number = course.get("courseNumber")
        if number is not None:
            numbers.append(str(number))
    return numbers


def _compact_semester_plan(plan: dict[str, Any]) -> dict[str, Any]:
    semesters = plan.get("semesters") or []
    primary = semesters[0] if semesters else {}
    planned_courses = primary.get("plannedCourses") or []
    constraints = primary.get("constraintsSnapshot") or {}

    return {
        "planId": str(plan.get("_id")) if plan.get("_id") is not None else None,
        "name": plan.get("name"),
        "status": plan.get("status"),
        "plannerType": plan.get("plannerType"),
        "semesterCode": primary.get("semesterCode"),
        "goalCredits": primary.get("goalCredits"),
        "maxCredits": constraints.get("maxCredits") or primary.get("goalCredits"),
        "plannedCourseNumbers": _course_numbers_from_planned_courses(planned_courses),
        "plannedCourseCount": len(planned_courses),
        "explanationSummary": (plan.get("explanation") or {}).get("summary"),
    }


def _compact_risk_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    summary = analysis.get("summary") or {}
    risks = analysis.get("risks") or []
    top_risks = [
        {
            "severity": item.get("severity"),
            "title": item.get("title"),
            "riskType": item.get("riskType"),
        }
        for item in risks[:3]
        if isinstance(item, dict)
    ]
    return {
        "analysisId": str(analysis.get("_id")) if analysis.get("_id") is not None else None,
        "semesterCode": analysis.get("semesterCode"),
        "status": analysis.get("status"),
        "highestSeverity": summary.get("highestSeverity"),
        "totalRisks": summary.get("totalRisks"),
        "topRisks": top_risks,
    }


async def build_planning_context_envelope(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any]:
    """
    Pre-compute deterministic planner outputs for the AI planning swarm.
    The AI service reads this envelope via in-memory tools (no direct API calls).
    """
    progress_result = await get_graduation_progress_for_user(database, user_id)
    status = progress_result.get("status")
    if status != "ok":
        return {"status": status, "available": False}

    progress = progress_result.get("progress") or {}
    envelope: dict[str, Any] = {
        "status": "ok",
        "available": True,
        "graduation": _compact_graduation(progress),
        "latest_plan": None,
        "latest_risk": None,
    }

    plans_page = await find_semester_plans_by_user_id(database, user_id, page=1, limit=1)
    plans = plans_page.get("plans") or []
    if plans:
        envelope["latest_plan"] = _compact_semester_plan(plans[0])

    risks_page = await find_academic_risk_analyses_by_user_id(database, user_id, page=1, limit=1)
    analyses = risks_page.get("analyses") or []
    if analyses:
        envelope["latest_risk"] = _compact_risk_analysis(analyses[0])

    return envelope
