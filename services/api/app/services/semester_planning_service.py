"""Generate semester plan options for the UniPilot Agent (spec §30.4)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.schemas.agent_context_snapshot import AgentContextSnapshot
from app.services.graduation_progress_calculator import round_credits
from app.services.semester_plan_suggestion_service import (
    suggest_semester_courses,
    suggest_semester_schedule,
)
from app.services.manual_semester_plan_service import create_manual_semester_plan
from app.repositories.semester_plan_repository import to_public_semester_plan

PlanningStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
    "validation_error",
    "no_options",
]


class SemesterPlanOption(BaseModel):
    optionId: str
    label: str
    description: str
    semesterCode: str
    maxCredits: float
    totalCredits: float
    courseCount: int
    plannedCourses: list[dict[str, Any]] = Field(default_factory=list)
    scheduleSelections: list[dict[str, Any]] = Field(default_factory=list)
    examSummary: dict[str, Any] = Field(default_factory=dict)
    skippedCourses: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    partialPlan: bool = False
    emptyPlan: bool = False


class SemesterPlanningResult(BaseModel):
    status: PlanningStatus = "ok"
    semesterCode: str | None = None
    options: list[SemesterPlanOption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


async def generate_semester_plan_options(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    context: AgentContextSnapshot,
) -> SemesterPlanningResult:
    if context.intent == "semester_plan_modification":
        modified = await _generate_modified_plan_options(database, user_id=user_id, context=context)
        if modified is not None:
            return modified

    semester_code = str(context.entities.get("targetSemesterCode") or "").strip() or None
    if not semester_code:
        return SemesterPlanningResult(
            status="validation_error",
            errors=["Target semester could not be resolved"],
            assumptions=["Specify a semester code or say 'next semester'."],
        )

    profile = context.user_context.get("profile") or {}
    preferences = profile.get("preferences") or {}
    default_max = round_credits(float(preferences.get("maxCreditsPerSemester") or 18.0))
    entity_max = context.entities.get("maxCredits")
    if entity_max is not None:
        default_max = round_credits(float(entity_max))

    variants = _build_credit_variants(
        default_max=default_max,
        planning_objective=str(context.entities.get("planningObjective") or ""),
    )

    options: list[SemesterPlanOption] = []
    warnings: list[str] = list(context.validation.warnings)
    assumptions: list[str] = []
    seen_signatures: set[tuple[str, ...]] = set()

    avoid_days = [str(day) for day in (context.entities.get("avoidDays") or []) if day]
    if avoid_days:
        assumptions.append(f"Avoid classes on: {', '.join(avoid_days)}")

    for index, (label, max_credits) in enumerate(variants):
        suggestion = await suggest_semester_courses(
            database,
            user_id,
            semester_code=semester_code,
            max_credits=max_credits,
        )
        if suggestion.get("status") != "ok":
            if not options and suggestion.get("status") in {
                "profile_not_found",
                "degree_not_selected",
                "degree_not_found",
            }:
                return SemesterPlanningResult(
                    status=suggestion["status"],
                    semesterCode=semester_code,
                    errors=list(suggestion.get("errors") or []),
                    assumptions=assumptions,
                )
            if suggestion.get("status") == "validation_error":
                return SemesterPlanningResult(
                    status="validation_error",
                    semesterCode=semester_code,
                    errors=list(suggestion.get("errors") or ["Invalid planning request"]),
                    assumptions=assumptions,
                )
            continue

        planned_courses = list(suggestion.get("plannedCourses") or [])
        explanation = suggestion.get("explanation") or {}
        signature = tuple(sorted(str(course.get("courseNumber") or "") for course in planned_courses))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        schedule_selections: list[dict[str, Any]] = []
        skipped_courses: list[dict[str, Any]] = []
        exam_summary: dict[str, Any] = {}
        if planned_courses:
            schedule = await suggest_semester_schedule(
                database,
                user_id,
                semester_code=semester_code,
                planned_courses=planned_courses,
            )
            if schedule.get("status") == "ok":
                schedule_selections = list(schedule.get("selections") or [])
                schedule_selections, avoid_conflicts = _filter_schedule_by_avoid_days(
                    schedule_selections,
                    avoid_days,
                )
                if avoid_conflicts:
                    warnings.append(
                        f"{len(avoid_conflicts)} course(s) conflict with avoided day preferences."
                    )
                skipped_courses = list(schedule.get("skippedCourses") or [])
                exam_summary = dict(schedule.get("examSummary") or {})

        total_credits = float(explanation.get("semesterTotalCredits") or 0)
        option_id = chr(ord("A") + index)
        option_warnings = _option_warnings(explanation, skipped_courses)
        pros, cons = _pros_and_cons(
            label=label,
            total_credits=total_credits,
            max_credits=max_credits,
            course_count=len(planned_courses),
            explanation=explanation,
        )

        options.append(
            SemesterPlanOption(
                optionId=option_id,
                label=label,
                description=_option_description(
                    label=label,
                    semester_code=semester_code,
                    total_credits=total_credits,
                    course_count=len(planned_courses),
                ),
                semesterCode=semester_code,
                maxCredits=max_credits,
                totalCredits=total_credits,
                courseCount=len(planned_courses),
                plannedCourses=planned_courses,
                scheduleSelections=schedule_selections,
                examSummary=exam_summary,
                skippedCourses=skipped_courses,
                warnings=option_warnings,
                pros=pros,
                cons=cons,
                partialPlan=bool(explanation.get("partialPlan")),
                emptyPlan=bool(explanation.get("emptyPlan")),
            )
        )

        if len(options) >= 5:
            break

    if not options:
        return SemesterPlanningResult(
            status="no_options",
            semesterCode=semester_code,
            warnings=warnings,
            assumptions=assumptions,
            errors=["No viable semester plan options could be generated for the requested semester."],
        )

    return SemesterPlanningResult(
        status="ok",
        semesterCode=semester_code,
        options=options,
        warnings=warnings,
        assumptions=assumptions,
    )


async def save_semester_plan_option(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    option: dict[str, Any],
) -> dict[str, Any]:
    """Persist a confirmed semester plan option as a draft manual plan."""
    semester_code = str(option.get("semesterCode") or "")
    planned_courses = list(option.get("plannedCourses") or [])
    if not semester_code or not planned_courses:
        return {"status": "validation_error", "errors": ["Plan option is missing semester or courses"]}

    weekly_schedule = _weekly_schedule_from_selections(option.get("scheduleSelections") or [])
    payload = {
        "name": str(option.get("label") or "Agent semester plan"),
        "semesterCode": semester_code,
        "goalCredits": option.get("totalCredits"),
        "plannedCourses": planned_courses,
        "weeklySchedule": weekly_schedule,
        "status": "draft",
        "notes": option.get("description"),
    }
    result = await create_manual_semester_plan(database, user_id, payload)
    if result.get("status") != "ok":
        return result
    public_plan = to_public_semester_plan(result.get("plan"))
    return {"status": "ok", "plan": public_plan}


def _build_credit_variants(*, default_max: float, planning_objective: str) -> list[tuple[str, float]]:
    lighter = round_credits(max(8.0, default_max - 4.0))
    faster = round_credits(min(26.0, default_max + 3.0))

    if planning_objective == "lighter_workload":
        return [("Lighter workload", lighter), ("Balanced", default_max)]
    if planning_objective == "heavier_workload":
        return [("Faster progress", faster), ("Balanced", default_max)]

    variants = [
        ("Balanced", default_max),
        ("Lighter workload", lighter),
        ("Faster progress", faster),
    ]
    deduped: list[tuple[str, float]] = []
    seen: set[float] = set()
    for label, credits in variants:
        if credits in seen:
            continue
        seen.add(credits)
        deduped.append((label, credits))
    return deduped


def _option_description(*, label: str, semester_code: str, total_credits: float, course_count: int) -> str:
    return (
        f"{label} plan for {semester_code}: {course_count} course(s), "
        f"{total_credits:g} total credits."
    )


def _option_warnings(
    explanation: dict[str, Any],
    skipped_courses: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if explanation.get("partialPlan"):
        warnings.append("partial_plan")
    if explanation.get("emptyPlan"):
        warnings.append("empty_plan")
    skipped_workload = explanation.get("skippedDueToWorkload") or []
    if skipped_workload:
        warnings.append("courses_skipped_due_to_workload")
    if skipped_courses:
        warnings.append("courses_skipped_in_schedule")
    return warnings


def _pros_and_cons(
    *,
    label: str,
    total_credits: float,
    max_credits: float,
    course_count: int,
    explanation: dict[str, Any],
) -> tuple[list[str], list[str]]:
    pros = [f"Covers {course_count} recommended course(s) for {label.lower()}."]
    if total_credits <= max_credits:
        pros.append(f"Stays within {max_credits:g} credit limit.")
    if explanation.get("activeMatrixSemester"):
        pros.append(f"Advances matrix semester {explanation['activeMatrixSemester']}.")

    cons: list[str] = []
    if explanation.get("partialPlan"):
        cons.append("Does not fill the full credit target because of eligibility or offerings.")
    if explanation.get("skippedDueToConflicts"):
        cons.append("Some courses were skipped due to schedule or exam conflicts.")
    if explanation.get("emptyPlan"):
        cons.append("No courses could be selected for this option.")
    return pros, cons


def _weekly_schedule_from_selections(selections: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not selections:
        return None
    events: list[dict[str, Any]] = []
    for selection in selections:
        for event in selection.get("lessonEvents") or selection.get("selectedLessonEvents") or []:
            if isinstance(event, dict):
                events.append(event)
    if not events:
        return {"events": selections}
    return {"events": events}


def _filter_schedule_by_avoid_days(
    selections: list[dict[str, Any]],
    avoid_days: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not avoid_days:
        return selections, []
    avoid_set = {day.strip().lower() for day in avoid_days if day}
    kept: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for selection in selections:
        events = selection.get("lessonEvents") or selection.get("selectedLessonEvents") or []
        has_conflict = any(
            str(event.get("day") or event.get("weekday") or "").strip().lower() in avoid_set
            for event in events
            if isinstance(event, dict)
        )
        if has_conflict:
            conflicts.append(selection)
        else:
            kept.append(selection)
    return kept, conflicts


def _select_base_plan(context: AgentContextSnapshot) -> dict[str, Any] | None:
    plans = context.user_context.get("semesterPlans") or []
    if not plans:
        return None
    plan_id = str(context.entities.get("planId") or "").strip()
    if plan_id:
        for plan in plans:
            if str(plan.get("id")) == plan_id:
                return plan
    return plans[0]


def _apply_plan_modifications(
    planned_courses: list[dict[str, Any]],
    *,
    entities: dict[str, Any],
) -> list[dict[str, Any]]:
    updated = [dict(course) for course in planned_courses if isinstance(course, dict)]
    replace_number = str(entities.get("replaceCourseNumber") or "").strip()
    add_number = str(entities.get("addCourseNumber") or "").strip()
    if replace_number and updated:
        updated[0] = {**updated[0], "courseNumber": replace_number, "courseId": replace_number}
    if add_number and not any(str(c.get("courseNumber")) == add_number for c in updated):
        updated.append({"courseNumber": add_number, "courseId": add_number})
    return updated


async def _generate_modified_plan_options(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    context: AgentContextSnapshot,
) -> SemesterPlanningResult | None:
    base_plan = _select_base_plan(context)
    if not base_plan:
        return SemesterPlanningResult(
            status="validation_error",
            errors=["No saved semester plan found to modify."],
            assumptions=["Generate a semester plan first, then ask to modify it."],
        )

    semester_code = str(
        context.entities.get("targetSemesterCode") or base_plan.get("semesterCode") or ""
    ).strip()
    if not semester_code:
        return SemesterPlanningResult(
            status="validation_error",
            errors=["Could not determine semester code for the saved plan."],
        )

    planned_courses = _apply_plan_modifications(
        list(base_plan.get("plannedCourses") or []),
        entities=context.entities,
    )
    profile = context.user_context.get("profile") or {}
    preferences = profile.get("preferences") or {}
    default_max = round_credits(float(preferences.get("maxCreditsPerSemester") or 18.0))
    entity_max = context.entities.get("maxCredits")
    if entity_max is not None:
        default_max = round_credits(float(entity_max))
    if context.entities.get("planningObjective") == "lighter_workload":
        default_max = round_credits(max(8.0, default_max - 4.0))

    avoid_days = [str(day) for day in (context.entities.get("avoidDays") or []) if day]
    assumptions = [
        f"Modifying saved plan: {base_plan.get('name') or 'Semester plan'}",
        *([f"Avoid classes on: {', '.join(avoid_days)}"] if avoid_days else []),
    ]
    warnings: list[str] = list(context.validation.warnings)

    schedule_selections: list[dict[str, Any]] = []
    skipped_courses: list[dict[str, Any]] = []
    exam_summary: dict[str, Any] = {}
    if planned_courses:
        schedule = await suggest_semester_schedule(
            database,
            user_id,
            semester_code=semester_code,
            planned_courses=planned_courses,
        )
        if schedule.get("status") == "ok":
            schedule_selections = list(schedule.get("selections") or [])
            schedule_selections, avoid_conflicts = _filter_schedule_by_avoid_days(
                schedule_selections,
                avoid_days,
            )
            if avoid_conflicts:
                warnings.append(
                    f"{len(avoid_conflicts)} course(s) conflict with avoided day preferences."
                )
            skipped_courses = list(schedule.get("skippedCourses") or [])
            exam_summary = dict(schedule.get("examSummary") or {})

    total_credits = sum(float(course.get("credits") or 0) for course in planned_courses)
    option = SemesterPlanOption(
        optionId="U",
        label="Updated plan",
        description=f"Updated version of {base_plan.get('name') or 'your saved plan'} for {semester_code}.",
        semesterCode=semester_code,
        maxCredits=default_max,
        totalCredits=total_credits,
        courseCount=len(planned_courses),
        plannedCourses=planned_courses,
        scheduleSelections=schedule_selections,
        examSummary=exam_summary,
        skippedCourses=skipped_courses,
        warnings=warnings,
        pros=["Preserves existing course choices where possible."],
        cons=(["Some schedule groups conflict with day preferences."] if warnings else []),
        partialPlan=len(schedule_selections) < len(planned_courses),
        emptyPlan=not planned_courses,
    )
    return SemesterPlanningResult(
        status="ok",
        semesterCode=semester_code,
        options=[option],
        warnings=warnings,
        assumptions=assumptions,
    )
