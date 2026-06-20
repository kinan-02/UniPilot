"""Manual semester plan validation and assembly (Phase 16.1)."""

from __future__ import annotations

from typing import Any

from app.planning.weekly_schedule import build_weekly_schedule_payload
from app.repositories import catalog_repository
from app.services.graduation_progress_calculator import round_credits


ALLOWED_PLAN_STATUSES = frozenset({"draft", "active"})
UPDATABLE_PLAN_STATUSES = frozenset({"draft", "active"})


def _normalize_course_id(course_id: Any) -> str:
    return str(course_id)


def _course_title(course: dict[str, Any]) -> str:
    return str(course.get("titleHebrew") or course.get("title") or "")


def _course_credits(course: dict[str, Any]) -> float:
    return round_credits(course.get("credits") or 0)


def build_manual_planned_course(
    course: dict[str, Any],
    *,
    category: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "courseId": _normalize_course_id(course["_id"]),
        "courseNumber": str(course.get("courseNumber") or course.get("number") or ""),
        "courseTitle": _course_title(course),
        "credits": _course_credits(course),
        "category": category or "manual",
        "reason": reason or "Added manually by student",
    }


def _find_offering_match(
    offerings: list[dict[str, Any]],
    *,
    academic_year: int,
    semester_code: int,
) -> dict[str, Any] | None:
    for offering in offerings:
        if offering.get("academicYear") == academic_year and offering.get("semesterCode") == semester_code:
            return offering
    return None


async def resolve_weekly_schedule_entries(
    database,
    *,
    planned_courses: list[dict[str, Any]],
    schedule_inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    planned_by_id = {_normalize_course_id(course["courseId"]): course for course in planned_courses}
    errors: list[str] = []
    built_entries: list[dict[str, Any]] = []

    for schedule_input in schedule_inputs:
        course_id = _normalize_course_id(schedule_input["courseId"])
        planned = planned_by_id.get(course_id)
        if not planned:
            errors.append(f"Weekly schedule references courseId {course_id} not in plannedCourses")
            continue

        course_number = planned["courseNumber"]
        academic_year = int(schedule_input["academicYear"])
        semester_code = int(schedule_input["semesterCode"])
        schedule_groups = schedule_input.get("scheduleGroups")

        if not schedule_groups:
            offerings = await catalog_repository.list_offerings_for_course(
                database,
                course_number,
                academic_year=academic_year,
                semester_code=semester_code,
            )
            offering = _find_offering_match(
                offerings,
                academic_year=academic_year,
                semester_code=semester_code,
            )
            if not offering:
                errors.append(
                    f"No published offering for course {course_number} "
                    f"in {academic_year} semesterCode {semester_code}"
                )
                continue
            schedule_groups = offering.get("scheduleGroups") or []

        if not schedule_groups:
            errors.append(f"Offering for course {course_number} has no scheduleGroups")
            continue

        built_entries.append(
            {
                "courseId": course_id,
                "courseNumber": course_number,
                "courseTitle": planned["courseTitle"],
                "academicYear": academic_year,
                "semesterCode": semester_code,
                "scheduleGroups": schedule_groups,
            }
        )

    return built_entries, errors


async def build_manual_semester_payload(
    database,
    *,
    semester_code: str,
    goal_credits: float | None,
    order: int | None,
    notes: str | None,
    planned_course_inputs: list[dict[str, Any]],
    weekly_schedule_input: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not planned_course_inputs:
        return None, ["plannedCourses must contain at least one course"]

    course_ids = [_normalize_course_id(item["courseId"]) for item in planned_course_inputs]
    if len(course_ids) != len(set(course_ids)):
        return None, ["Duplicate courseId in plannedCourses"]

    catalog_courses = await catalog_repository.find_courses_by_ids(database, course_ids)
    catalog_by_id = {_normalize_course_id(course["_id"]): course for course in catalog_courses}

    missing_ids = [course_id for course_id in course_ids if course_id not in catalog_by_id]
    if missing_ids:
        return None, [f"Unknown catalog courseId: {missing_id}" for missing_id in missing_ids]

    planned_courses: list[dict[str, Any]] = []
    for item in planned_course_inputs:
        course = catalog_by_id[_normalize_course_id(item["courseId"])]
        planned_courses.append(
            build_manual_planned_course(
                course,
                category=item.get("category"),
                reason=item.get("reason"),
            )
        )

    total_credits = round_credits(sum(course["credits"] for course in planned_courses))
    semester_payload: dict[str, Any] = {
        "semesterCode": semester_code,
        "goalCredits": goal_credits if goal_credits is not None else total_credits,
        "order": order if order is not None else 1,
        "plannedCourses": planned_courses,
        "notes": notes or "",
        "constraintsSnapshot": {},
    }

    if weekly_schedule_input is not None:
        schedule_entries, schedule_errors = await resolve_weekly_schedule_entries(
            database,
            planned_courses=planned_courses,
            schedule_inputs=weekly_schedule_input.get("entries") or [],
        )
        if schedule_errors:
            return None, schedule_errors
        semester_payload["weeklySchedule"] = build_weekly_schedule_payload(schedule_entries)

    return semester_payload, []


def build_manual_plan_document(
    *,
    name: str,
    semesters: list[dict[str, Any]],
    status: str = "draft",
) -> dict[str, Any]:
    primary = semesters[0]
    total_credits = round_credits(
        sum(course.get("credits") or 0 for course in primary.get("plannedCourses") or [])
    )
    return {
        "name": name,
        "status": status,
        "version": 1,
        "plannerType": "manual",
        "assumptions": {
            "createdBy": "manual",
            "editable": True,
        },
        "explanation": {
            "summary": f"Manual plan with {len(primary.get('plannedCourses') or [])} course(s)",
            "totalRecommendedCredits": total_credits,
            "rulesApplied": ["manual_selection"],
            "partialPlan": False,
            "emptyPlan": len(primary.get("plannedCourses") or []) == 0,
        },
        "semesters": semesters,
    }


def validate_status_transition(current_status: str, next_status: str | None) -> str | None:
    if next_status is None:
        return None
    if next_status not in ALLOWED_PLAN_STATUSES:
        return f"status must be one of: {', '.join(sorted(ALLOWED_PLAN_STATUSES))}"
    if current_status == "archived":
        return "Archived semester plans cannot be updated"
    return None


def collect_course_ids_across_semesters(semesters: list[dict[str, Any]]) -> list[str]:
    course_ids: list[str] = []
    for semester in semesters:
        for course in semester.get("plannedCourses") or []:
            course_ids.append(_normalize_course_id(course["courseId"]))
    return course_ids


async def _build_semesters_from_request(
    database,
    *,
    semesters_payload: list[dict[str, Any]] | None,
    single_semester_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    built_semesters: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    inputs = semesters_payload or []
    if single_semester_payload is not None:
        inputs = [single_semester_payload]

    for index, semester_input in enumerate(inputs, start=1):
        semester_payload, errors = await build_manual_semester_payload(
            database,
            semester_code=semester_input["semesterCode"],
            goal_credits=semester_input.get("goalCredits"),
            order=semester_input.get("order", index),
            notes=semester_input.get("notes"),
            planned_course_inputs=semester_input["plannedCourses"],
            weekly_schedule_input=semester_input.get("weeklySchedule"),
        )
        if errors:
            validation_errors.extend(errors)
            continue
        if semester_payload:
            built_semesters.append(semester_payload)

    if validation_errors:
        return None, validation_errors

    all_course_ids = collect_course_ids_across_semesters(built_semesters)
    if len(all_course_ids) != len(set(all_course_ids)):
        return None, ["The same courseId cannot appear in more than one semester"]

    return built_semesters, []


async def load_manual_plan_context(
    database,
    user_id: str,
) -> dict[str, Any]:
    """Manual plans only require an existing profile — not degree or completed courses."""
    from app.repositories.student_profile_repository import find_student_profile_by_user_id

    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found"}
    return {"status": "ok", "profile": profile}


async def create_manual_semester_plan(
    database,
    user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import create_semester_plan

    context = await load_manual_plan_context(database, user_id)
    if context["status"] != "ok":
        return context

    single_semester_payload = None
    if not payload.get("semesters"):
        single_semester_payload = {
            "semesterCode": payload["semesterCode"],
            "goalCredits": payload.get("goalCredits"),
            "order": 1,
            "notes": payload.get("notes"),
            "plannedCourses": payload["plannedCourses"],
            "weeklySchedule": payload.get("weeklySchedule"),
        }

    semesters, errors = await _build_semesters_from_request(
        database,
        semesters_payload=payload.get("semesters"),
        single_semester_payload=single_semester_payload,
    )
    if errors:
        return {"status": "validation_error", "errors": errors}

    plan_data = build_manual_plan_document(
        name=payload["name"],
        semesters=semesters or [],
        status=payload.get("status", "draft"),
    )
    stored_plan = await create_semester_plan(database, user_id, plan_data)
    return {"status": "ok", "plan": stored_plan}


async def update_semester_plan_by_user(
    database,
    user_id: str,
    plan_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}

    current_status = str(existing_plan.get("status") or "draft")
    if current_status == "archived":
        return {"status": "archived"}

    status_error = validate_status_transition(current_status, payload.get("status"))
    if status_error:
        return {"status": "validation_error", "errors": [status_error]}

    updates: dict[str, Any] = {}
    if payload.get("name") is not None:
        updates["name"] = payload["name"]
    if payload.get("status") is not None:
        updates["status"] = payload["status"]

    if payload.get("semesters") is not None:
        semesters, errors = await _build_semesters_from_request(
            database,
            semesters_payload=payload["semesters"],
            single_semester_payload=None,
        )
        if errors:
            return {"status": "validation_error", "errors": errors}
        updates["semesters"] = semesters

        primary = (semesters or [{}])[0]
        total_credits = round_credits(
            sum(course.get("credits") or 0 for course in primary.get("plannedCourses") or [])
        )
        explanation = dict(existing_plan.get("explanation") or {})
        explanation.update(
            {
                "summary": f"Manual plan with {len(primary.get('plannedCourses') or [])} course(s)",
                "totalRecommendedCredits": total_credits,
                "emptyPlan": len(primary.get("plannedCourses") or []) == 0,
            }
        )
        updates["explanation"] = explanation
        updates["plannerType"] = "manual"

    if not updates:
        return {"status": "validation_error", "errors": ["No updatable fields provided"]}

    next_version = int(existing_plan.get("version") or 1) + 1
    updates["version"] = next_version

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        updates,
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def create_semester_plan_version_by_user(
    database,
    user_id: str,
    plan_id: str,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import (
        create_semester_plan_version_from_source,
        find_semester_plan_by_id_and_user_id,
    )

    source_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not source_plan:
        return {"status": "not_found"}
    if source_plan.get("status") == "archived":
        return {"status": "archived_source"}

    stored_plan = await create_semester_plan_version_from_source(
        database,
        user_id,
        source_plan,
        name=name,
    )
    return {"status": "ok", "plan": stored_plan, "sourcePlanId": plan_id}


async def archive_semester_plan_by_user(
    database,
    user_id: str,
    plan_id: str,
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "ok", "plan": existing_plan}

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {"status": "archived"},
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}
