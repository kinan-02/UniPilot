"""Deterministic what-if simulation runner (API-side, no LLM)."""

from __future__ import annotations

import copy
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.academic_risk_analyzer import analyze_academic_risks
from app.repositories.semester_plan_repository import find_semester_plan_by_id_and_user_id
from app.services.academic_risk_service import build_plan_view_from_adhoc, build_plan_view_from_semester_plan
from app.services.graduation_progress_calculator import calculate_graduation_progress
from app.services.semester_plan_service import load_planning_context
from app.services.simulation_ops import (
    apply_transcript_operations,
    collect_planned_course_numbers,
    collect_track_change,
)
from app.services.simulation_snapshots import (
    build_progress_delta,
    build_risk_delta,
    build_template_summary,
    compact_graduation_progress,
    compact_risk_analysis,
)


async def _build_plan_view(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario: dict[str, Any],
    *,
    degree: dict[str, Any],
    planned_numbers: list[str],
) -> dict[str, Any] | None:
    if scenario.get("planId"):
        plan = await find_semester_plan_by_id_and_user_id(
            database,
            str(scenario["planId"]),
            user_id,
        )
        if plan:
            plan_view = build_plan_view_from_semester_plan(plan)
            if planned_numbers:
                existing_numbers = {
                    str(course.get("courseNumber"))
                    for course in plan_view.get("plannedCourses") or []
                    if course.get("courseNumber")
                }
                for number in planned_numbers:
                    if number not in existing_numbers:
                        plan_view["plannedCourses"] = list(plan_view.get("plannedCourses") or []) + [
                            {"courseNumber": number, "category": "simulation"}
                        ]
            return plan_view

    if not planned_numbers:
        return None

    semester_code = scenario.get("semesterCode")
    if not semester_code:
        return None

    from app.repositories import catalog_repository

    course_ids: list[str] = []
    for number in planned_numbers:
        course = await catalog_repository.find_course_by_number(database, number)
        if course:
            course_ids.append(str(course["_id"]))

    if not course_ids:
        return None

    return await build_plan_view_from_adhoc(
        database,
        degree,
        {
            "semesterCode": semester_code,
            "courseIds": course_ids,
        },
    )


def _analyze_risk_snapshot(
    context: dict[str, Any],
    *,
    completed_records: list[dict[str, Any]],
    plan_view: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not plan_view:
        return None

    return analyze_academic_risks(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        pool_documents=context["poolDocuments"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=completed_records,
        plan_view=plan_view,
    )


async def run_deterministic_simulation(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    operations = scenario.get("operations") or []
    profile = copy.deepcopy(context["profile"])
    track_slug = collect_track_change(operations)
    if track_slug:
        academic_path = dict(profile.get("academicPath") or {})
        academic_path["trackSlug"] = track_slug
        profile["academicPath"] = academic_path

    default_semester = scenario.get("semesterCode") or profile.get("currentSemesterCode")
    baseline_records = copy.deepcopy(context["completedCourseRecords"])
    modified_records, warnings = await apply_transcript_operations(
        database,
        baseline_records,
        operations,
        default_semester_code=default_semester,
    )

    planned_numbers = collect_planned_course_numbers(operations)
    baseline_plan_view = await _build_plan_view(
        database,
        user_id,
        scenario,
        degree=context["degree"],
        planned_numbers=[],
    )
    after_plan_view = await _build_plan_view(
        database,
        user_id,
        scenario,
        degree=context["degree"],
        planned_numbers=planned_numbers,
    )

    baseline_progress = context["graduationProgress"]
    after_progress = calculate_graduation_progress(
        degree_program=context["degree"],
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        catalog_courses_by_id={
            str(course["_id"]): course for course in context["catalogCourses"]
        },
        completed_course_records=modified_records,
        semester_matrix_documents=context["semesterMatrixDocuments"],
    )

    baseline_context = {**context, "graduationProgress": baseline_progress}
    after_context = {**context, "graduationProgress": after_progress, "profile": profile}

    baseline_risk_raw = _analyze_risk_snapshot(
        baseline_context,
        completed_records=baseline_records,
        plan_view=baseline_plan_view or after_plan_view,
    )
    after_risk_raw = _analyze_risk_snapshot(
        after_context,
        completed_records=modified_records,
        plan_view=after_plan_view or baseline_plan_view,
    )

    before_progress = compact_graduation_progress(baseline_progress)
    after_progress_compact = compact_graduation_progress(after_progress)
    before_risk = compact_risk_analysis(baseline_risk_raw) if baseline_risk_raw else None
    after_risk = compact_risk_analysis(after_risk_raw) if after_risk_raw else None

    progress_delta = build_progress_delta(before_progress, after_progress_compact)
    risk_delta = build_risk_delta(before_risk, after_risk)
    summary = build_template_summary(
        str(scenario.get("name") or "Simulation"),
        progress_delta=progress_delta,
        risk_delta=risk_delta,
    )

    return {
        "status": "ok",
        "beforeSnapshot": {
            "graduation": before_progress,
            "risk": before_risk,
            "trackSlug": (profile.get("academicPath") or {}).get("trackSlug"),
        },
        "afterSnapshot": {
            "graduation": after_progress_compact,
            "risk": after_risk,
            "trackSlug": track_slug or (profile.get("academicPath") or {}).get("trackSlug"),
        },
        "deltas": {
            "progress": progress_delta,
            "risk": risk_delta,
        },
        "summary": summary,
        "warnings": warnings,
    }
