"""Manual semester plan validation and assembly (Phase 16.1)."""

from __future__ import annotations

from typing import Any

from app.planning.lesson_events import (
    extract_lesson_options_from_offering,
    sync_selected_groups_from_events,
    validate_lesson_selection,
)
from app.planning.schedule_group_selection import filter_schedule_groups_by_selection
from app.planning.semester_codes import pick_best_offering
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
    is_active: bool = True,
    selected_groups: dict[str, Any] | None = None,
    selected_lesson_events: list[dict[str, Any]] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "courseId": _normalize_course_id(course["_id"]),
        "courseNumber": str(course.get("courseNumber") or course.get("number") or ""),
        "courseTitle": _course_title(course),
        "credits": _course_credits(course),
        "category": category or "manual",
        "reason": reason or "Added manually by student",
        "isActive": is_active,
        "selectedLessonEvents": selected_lesson_events or [],
        "selectedGroups": selected_groups
        or {"lecture": [], "tutorial": [], "lab": [], "project": []},
        "notes": notes,
    }


def _default_selected_groups() -> dict[str, Any]:
    return {"lecture": [], "tutorial": [], "lab": [], "project": []}


def _selected_groups_from_input(item: dict[str, Any]) -> dict[str, Any] | None:
    selected = item.get("selectedGroups")
    if selected is None:
        return None
    if hasattr(selected, "model_dump"):
        return selected.model_dump()
    return dict(selected)


def _selected_lesson_events_from_input(item: dict[str, Any]) -> list[dict[str, Any]] | None:
    selected = item.get("selectedLessonEvents")
    if selected is None:
        return None
    events: list[dict[str, Any]] = []
    for event in selected:
        if hasattr(event, "model_dump"):
            events.append(event.model_dump())
        else:
            events.append(dict(event))
    return events


def is_course_active(planned_course: dict[str, Any]) -> bool:
    return planned_course.get("isActive", True) is not False


def _find_offering_match(
    offerings: list[dict[str, Any]],
    *,
    academic_year: int,
    semester_code: int,
) -> dict[str, Any] | None:
    return pick_best_offering(
        offerings,
        preferred_academic_year=academic_year,
        semester_code=semester_code,
    )


async def _load_offering_for_schedule(
    database,
    *,
    course_number: str,
    academic_year: int,
    semester_code: int,
) -> dict[str, Any] | None:
    """Load offering for plan semester; fall back to nearest catalog year for same term."""
    offerings_by_number = await catalog_repository.list_best_offerings_for_courses(
        database,
        [course_number],
        academic_year=academic_year,
        semester_code=semester_code,
    )
    return offerings_by_number.get(course_number)


async def resolve_weekly_schedule_entries(
    database,
    *,
    planned_courses: list[dict[str, Any]],
    schedule_inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    planned_by_id = {_normalize_course_id(course["courseId"]): course for course in planned_courses}
    errors: list[str] = []
    built_entries: list[dict[str, Any]] = []

    needs_offering: list[tuple[dict[str, Any], dict[str, Any], str, int, int]] = []
    for schedule_input in schedule_inputs:
        course_id = _normalize_course_id(schedule_input["courseId"])
        planned = planned_by_id.get(course_id)
        if not planned:
            errors.append(f"Weekly schedule references courseId {course_id} not in plannedCourses")
            continue
        if not is_course_active(planned):
            continue
        if schedule_input.get("scheduleGroups"):
            continue
        needs_offering.append(
            (
                schedule_input,
                planned,
                planned["courseNumber"],
                int(schedule_input["academicYear"]),
                int(schedule_input["semesterCode"]),
            )
        )

    offerings_by_number: dict[str, dict[str, Any]] = {}
    if needs_offering:
        by_term: dict[tuple[int, int], list[str]] = {}
        for _, _, course_number, academic_year, semester_code in needs_offering:
            by_term.setdefault((academic_year, semester_code), []).append(course_number)
        for (academic_year, semester_code), numbers in by_term.items():
            batch = await catalog_repository.list_best_offerings_for_courses(
                database,
                numbers,
                academic_year=academic_year,
                semester_code=semester_code,
            )
            offerings_by_number.update(batch)

    for schedule_input in schedule_inputs:
        course_id = _normalize_course_id(schedule_input["courseId"])
        planned = planned_by_id.get(course_id)
        if not planned:
            errors.append(f"Weekly schedule references courseId {course_id} not in plannedCourses")
            continue
        if not is_course_active(planned):
            continue

        course_number = planned["courseNumber"]
        academic_year = int(schedule_input["academicYear"])
        semester_code = int(schedule_input["semesterCode"])
        schedule_groups = schedule_input.get("scheduleGroups")

        if not schedule_groups:
            offering = offerings_by_number.get(course_number)
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

        schedule_groups = filter_schedule_groups_by_selection(
            schedule_groups,
            planned.get("selectedGroups"),
            selected_lesson_events=planned.get("selectedLessonEvents"),
            course_number=course_number,
            academic_year=academic_year,
            semester_code=semester_code,
        )
        if not schedule_groups:
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


async def _build_planned_course_list_from_inputs(
    database,
    planned_course_inputs: list[dict[str, Any]],
    *,
    field_label: str,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    if not planned_course_inputs:
        return [], []

    course_ids = [_normalize_course_id(item["courseId"]) for item in planned_course_inputs]
    if len(course_ids) != len(set(course_ids)):
        return None, [f"Duplicate courseId in {field_label}"]

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
                is_active=item.get("isActive", True),
                selected_groups=_selected_groups_from_input(item),
                selected_lesson_events=_selected_lesson_events_from_input(item),
                notes=item.get("notes"),
            )
        )
    return planned_courses, []


async def build_manual_semester_payload(
    database,
    *,
    semester_code: str,
    goal_credits: float | None,
    order: int | None,
    notes: str | None,
    planned_course_inputs: list[dict[str, Any]],
    maybe_course_inputs: list[dict[str, Any]] | None = None,
    weekly_schedule_input: dict[str, Any] | None,
    custom_events: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    maybe_inputs = maybe_course_inputs or []
    if not planned_course_inputs and not maybe_inputs:
        return None, ["plannedCourses or maybeCourses must contain at least one course"]

    planned_courses, planned_errors = await _build_planned_course_list_from_inputs(
        database,
        planned_course_inputs,
        field_label="plannedCourses",
    )
    if planned_errors:
        return None, planned_errors
    assert planned_courses is not None

    maybe_courses, maybe_errors = await _build_planned_course_list_from_inputs(
        database,
        maybe_course_inputs or [],
        field_label="maybeCourses",
    )
    if maybe_errors:
        return None, maybe_errors
    assert maybe_courses is not None

    planned_ids = {_normalize_course_id(course["courseId"]) for course in planned_courses}
    maybe_ids = {_normalize_course_id(course["courseId"]) for course in maybe_courses}
    overlap = planned_ids & maybe_ids
    if overlap:
        return None, [
            f"courseId {course_id} cannot appear in both plannedCourses and maybeCourses"
            for course_id in sorted(overlap)
        ]

    active_courses = [course for course in planned_courses if is_course_active(course)]
    total_credits = round_credits(sum(course["credits"] for course in active_courses))
    semester_payload: dict[str, Any] = {
        "semesterCode": semester_code,
        "goalCredits": goal_credits if goal_credits is not None else total_credits,
        "order": order if order is not None else 1,
        "plannedCourses": planned_courses,
        "maybeCourses": maybe_courses,
        "notes": notes or "",
        "constraintsSnapshot": {},
    }

    normalized_custom_events = [
        event.model_dump() if hasattr(event, "model_dump") else dict(event)
        for event in (custom_events or [])
    ]
    if normalized_custom_events:
        semester_payload["customEvents"] = normalized_custom_events

    if weekly_schedule_input is not None:
        planned_by_id = {_normalize_course_id(course["courseId"]): course for course in planned_courses}
        schedule_inputs = [
            entry
            for entry in (weekly_schedule_input.get("entries") or [])
            if entry.get("courseId")
            and is_course_active(planned_by_id.get(_normalize_course_id(entry["courseId"]), {}))
        ]
        schedule_entries, schedule_errors = await resolve_weekly_schedule_entries(
            database,
            planned_courses=planned_courses,
            schedule_inputs=schedule_inputs,
        )
        if schedule_errors:
            return None, schedule_errors
        semester_payload["weeklySchedule"] = build_weekly_schedule_payload(
            schedule_entries,
            custom_events=normalized_custom_events,
        )

    return semester_payload, []


def build_manual_plan_document(
    *,
    name: str,
    semesters: list[dict[str, Any]],
    status: str = "draft",
) -> dict[str, Any]:
    primary = semesters[0]
    active_courses = [
        course for course in (primary.get("plannedCourses") or []) if is_course_active(course)
    ]
    total_credits = round_credits(sum(course.get("credits") or 0 for course in active_courses))
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
            "summary": f"Manual plan with {len(active_courses)} active course(s)",
            "totalRecommendedCredits": total_credits,
            "rulesApplied": ["manual_selection"],
            "partialPlan": False,
            "emptyPlan": len(active_courses) == 0,
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
        for course in semester.get("maybeCourses") or []:
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
            maybe_course_inputs=semester_input.get("maybeCourses"),
            weekly_schedule_input=semester_input.get("weeklySchedule"),
            custom_events=semester_input.get("customEvents"),
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
            "maybeCourses": payload.get("maybeCourses"),
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
        active_courses = [
            course for course in (primary.get("plannedCourses") or []) if is_course_active(course)
        ]
        total_credits = round_credits(sum(course.get("credits") or 0 for course in active_courses))
        explanation = dict(existing_plan.get("explanation") or {})
        explanation.update(
            {
                "summary": f"Manual plan with {len(active_courses)} active course(s)",
                "totalRecommendedCredits": total_credits,
                "emptyPlan": len(active_courses) == 0,
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


async def _rebuild_weekly_schedule_for_semester(
    database,
    semester: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    from app.planning.semester_codes import plan_semester_to_offering_keys

    planned = semester.get("plannedCourses") or []
    offering_keys = plan_semester_to_offering_keys(str(semester.get("semesterCode") or ""))
    if not offering_keys:
        return build_weekly_schedule_payload(
            [],
            custom_events=semester.get("customEvents") or [],
        ), []

    academic_year, technion_code = offering_keys
    schedule_inputs = [
        {
            "courseId": course["courseId"],
            "academicYear": academic_year,
            "semesterCode": technion_code,
        }
        for course in planned
        if is_course_active(course)
    ]
    entries, errors = await resolve_weekly_schedule_entries(
        database,
        planned_courses=planned,
        schedule_inputs=schedule_inputs,
    )
    if errors:
        return None, errors
    return (
        build_weekly_schedule_payload(
            entries,
            custom_events=semester.get("customEvents") or [],
        ),
        [],
    )


async def patch_planned_course_by_user(
    database,
    user_id: str,
    plan_id: str,
    course_number: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    semesters = [dict(semester) for semester in existing_plan.get("semesters") or []]
    if not semesters:
        return {"status": "validation_error", "errors": ["Plan has no semesters"]}

    primary = semesters[0]
    planned_courses = [dict(course) for course in primary.get("plannedCourses") or []]
    target_index = next(
        (
            index
            for index, course in enumerate(planned_courses)
            if str(course.get("courseNumber") or "") == course_number
        ),
        None,
    )
    if target_index is None:
        return {
            "status": "validation_error",
            "errors": [f"Course {course_number} is not in this plan"],
        }

    course = planned_courses[target_index]
    if payload.get("isActive") is not None:
        course["isActive"] = bool(payload["isActive"])
    if payload.get("selectedGroups") is not None:
        selected = payload["selectedGroups"]
        course["selectedGroups"] = (
            selected.model_dump() if hasattr(selected, "model_dump") else dict(selected)
        )
    if payload.get("selectedLessonEvents") is not None:
        events = payload["selectedLessonEvents"]
        normalized_events = [
            event.model_dump() if hasattr(event, "model_dump") else dict(event)
            for event in events
        ]
        course["selectedLessonEvents"] = normalized_events
        course["selectedGroups"] = sync_selected_groups_from_events(normalized_events)

    if "notes" in payload:
        course["notes"] = payload.get("notes")

    planned_courses[target_index] = course
    primary["plannedCourses"] = planned_courses

    weekly_schedule, schedule_errors = await _rebuild_weekly_schedule_for_semester(
        database,
        primary,
    )
    if schedule_errors:
        return {"status": "validation_error", "errors": schedule_errors}
    primary["weeklySchedule"] = weekly_schedule
    semesters[0] = primary

    active_courses = [item for item in planned_courses if is_course_active(item)]
    total_credits = round_credits(sum(item.get("credits") or 0 for item in active_courses))
    explanation = dict(existing_plan.get("explanation") or {})
    explanation.update(
        {
            "summary": f"Manual plan with {len(active_courses)} active course(s)",
            "totalRecommendedCredits": total_credits,
            "emptyPlan": len(active_courses) == 0,
        }
    )

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {
            "semesters": semesters,
            "explanation": explanation,
            "version": int(existing_plan.get("version") or 1) + 1,
        },
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def patch_lesson_selection_by_user(
    database,
    user_id: str,
    plan_id: str,
    course_number: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.planning.semester_codes import plan_semester_to_offering_keys
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    semesters = [dict(semester) for semester in existing_plan.get("semesters") or []]
    if not semesters:
        return {"status": "validation_error", "errors": ["Plan has no semesters"]}

    primary = semesters[0]
    planned_courses = [dict(course) for course in primary.get("plannedCourses") or []]
    target_index = next(
        (
            index
            for index, course in enumerate(planned_courses)
            if str(course.get("courseNumber") or "") == course_number
        ),
        None,
    )
    if target_index is None:
        return {
            "status": "validation_error",
            "errors": [f"Course {course_number} is not in this plan"],
        }

    offering_keys = plan_semester_to_offering_keys(str(primary.get("semesterCode") or ""))
    if not offering_keys:
        return {"status": "validation_error", "errors": ["Invalid semester code"]}

    academic_year, technion_code = offering_keys
    offering = await _load_offering_for_schedule(
        database,
        course_number=course_number,
        academic_year=academic_year,
        semester_code=technion_code,
    )
    if not offering:
        return {
            "status": "validation_error",
            "errors": [
                f"No published offering for course {course_number} "
                f"in {academic_year} semesterCode {technion_code}"
            ],
        }

    raw_events = payload.get("selectedLessonEvents") or []
    selected_events = [
        event.model_dump() if hasattr(event, "model_dump") else dict(event)
        for event in raw_events
    ]
    available_options = extract_lesson_options_from_offering(offering, course_number=course_number)
    validation_errors = validate_lesson_selection(selected_events, available_options)
    if validation_errors:
        return {"status": "validation_error", "errors": validation_errors}

    course = planned_courses[target_index]
    course["selectedLessonEvents"] = selected_events
    course["selectedGroups"] = sync_selected_groups_from_events(selected_events)
    planned_courses[target_index] = course
    primary["plannedCourses"] = planned_courses

    weekly_schedule, schedule_errors = await _rebuild_weekly_schedule_for_semester(
        database,
        primary,
    )
    if schedule_errors:
        return {"status": "validation_error", "errors": schedule_errors}
    primary["weeklySchedule"] = weekly_schedule
    semesters[0] = primary

    active_courses = [item for item in planned_courses if is_course_active(item)]
    total_credits = round_credits(sum(item.get("credits") or 0 for item in active_courses))
    explanation = dict(existing_plan.get("explanation") or {})
    explanation.update(
        {
            "summary": f"Manual plan with {len(active_courses)} active course(s)",
            "totalRecommendedCredits": total_credits,
            "emptyPlan": len(active_courses) == 0,
        }
    )

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {
            "semesters": semesters,
            "explanation": explanation,
            "version": int(existing_plan.get("version") or 1) + 1,
        },
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def reorder_planned_courses_by_user(
    database,
    user_id: str,
    plan_id: str,
    course_ids: list[str],
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    semesters = [dict(semester) for semester in existing_plan.get("semesters") or []]
    if not semesters:
        return {"status": "validation_error", "errors": ["Plan has no semesters"]}

    primary = semesters[0]
    planned_courses = [dict(course) for course in primary.get("plannedCourses") or []]
    by_id = {_normalize_course_id(course["courseId"]): course for course in planned_courses}
    normalized_ids = [_normalize_course_id(course_id) for course_id in course_ids]

    if len(normalized_ids) != len(set(normalized_ids)):
        return {"status": "validation_error", "errors": ["Duplicate courseIds in reorder payload"]}
    if set(normalized_ids) != set(by_id.keys()):
        return {
            "status": "validation_error",
            "errors": ["Reorder payload must include every planned course exactly once"],
        }

    primary["plannedCourses"] = [by_id[course_id] for course_id in normalized_ids]
    semesters[0] = primary

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {
            "semesters": semesters,
            "version": int(existing_plan.get("version") or 1) + 1,
        },
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def patch_maybe_courses_by_user(
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
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    semesters = [dict(semester) for semester in existing_plan.get("semesters") or []]
    if not semesters:
        return {"status": "validation_error", "errors": ["Plan has no semesters"]}

    primary = semesters[0]
    planned_courses = primary.get("plannedCourses") or []
    maybe_inputs = [
        item.model_dump() if hasattr(item, "model_dump") else dict(item)
        for item in (payload.get("maybeCourses") or [])
    ]

    maybe_courses, maybe_errors = await _build_planned_course_list_from_inputs(
        database,
        maybe_inputs,
        field_label="maybeCourses",
    )
    if maybe_errors:
        return {"status": "validation_error", "errors": maybe_errors}
    assert maybe_courses is not None

    planned_ids = {_normalize_course_id(course["courseId"]) for course in planned_courses}
    maybe_ids = {_normalize_course_id(course["courseId"]) for course in maybe_courses}
    overlap = planned_ids & maybe_ids
    if overlap:
        return {
            "status": "validation_error",
            "errors": [
                f"courseId {course_id} cannot appear in both plannedCourses and maybeCourses"
                for course_id in sorted(overlap)
            ],
        }

    primary["maybeCourses"] = maybe_courses
    semesters[0] = primary

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {
            "semesters": semesters,
            "version": int(existing_plan.get("version") or 1) + 1,
        },
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def patch_maybe_lesson_selection_by_user(
    database,
    user_id: str,
    plan_id: str,
    course_number: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from app.planning.semester_codes import plan_semester_to_offering_keys
    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    semesters = [dict(semester) for semester in existing_plan.get("semesters") or []]
    if not semesters:
        return {"status": "validation_error", "errors": ["Plan has no semesters"]}

    primary = semesters[0]
    maybe_courses = [dict(course) for course in primary.get("maybeCourses") or []]
    target_index = next(
        (
            index
            for index, course in enumerate(maybe_courses)
            if str(course.get("courseNumber") or "") == course_number
        ),
        None,
    )
    if target_index is None:
        return {
            "status": "validation_error",
            "errors": [f"Course {course_number} is not in maybeCourses"],
        }

    offering_keys = plan_semester_to_offering_keys(str(primary.get("semesterCode") or ""))
    if not offering_keys:
        return {"status": "validation_error", "errors": ["Invalid semester code"]}

    academic_year, technion_code = offering_keys
    offering = await _load_offering_for_schedule(
        database,
        course_number=course_number,
        academic_year=academic_year,
        semester_code=technion_code,
    )
    if not offering:
        return {
            "status": "validation_error",
            "errors": [
                f"No published offering for course {course_number} "
                f"in {academic_year} semesterCode {technion_code}"
            ],
        }

    raw_events = payload.get("selectedLessonEvents") or []
    selected_events = [
        event.model_dump() if hasattr(event, "model_dump") else dict(event)
        for event in raw_events
    ]
    available_options = extract_lesson_options_from_offering(offering, course_number=course_number)
    validation_errors = validate_lesson_selection(selected_events, available_options)
    if validation_errors:
        return {"status": "validation_error", "errors": validation_errors}

    course = maybe_courses[target_index]
    course["selectedLessonEvents"] = selected_events
    course["selectedGroups"] = sync_selected_groups_from_events(selected_events)
    maybe_courses[target_index] = course
    primary["maybeCourses"] = maybe_courses
    semesters[0] = primary

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        {
            "semesters": semesters,
            "version": int(existing_plan.get("version") or 1) + 1,
        },
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


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
        {"status": "archived", "shareEnabled": False},
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def update_semester_plan_share_by_user(
    database,
    user_id: str,
    plan_id: str,
    *,
    share_enabled: bool,
) -> dict[str, Any]:
    import secrets

    from app.repositories.semester_plan_repository import (
        find_semester_plan_by_id_and_user_id,
        update_semester_plan_by_id_and_user_id,
    )

    existing_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if not existing_plan:
        return {"status": "not_found"}
    if existing_plan.get("status") == "archived":
        return {"status": "archived"}

    updates: dict[str, Any] = {"shareEnabled": bool(share_enabled)}
    if share_enabled and not existing_plan.get("shareToken"):
        updates["shareToken"] = secrets.token_urlsafe(24)

    updated_plan = await update_semester_plan_by_id_and_user_id(
        database,
        plan_id,
        user_id,
        updates,
    )
    if not updated_plan:
        return {"status": "not_found"}
    return {"status": "ok", "plan": updated_plan}


async def get_shared_semester_plan_by_token(
    database,
    share_token: str,
) -> dict[str, Any]:
    from app.repositories.semester_plan_repository import find_semester_plan_by_share_token

    plan = await find_semester_plan_by_share_token(database, share_token)
    if not plan:
        return {"status": "not_found"}
    if plan.get("status") == "archived":
        return {"status": "not_found"}
    return {"status": "ok", "plan": plan}
