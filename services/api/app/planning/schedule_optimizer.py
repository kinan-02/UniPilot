"""Conflict-aware course selection and weekly schedule optimization."""

from __future__ import annotations

import itertools
from typing import Any

from app.planning.exam_summary import build_exam_summary, exams_from_offering
from app.planning.lesson_events import extract_lesson_options_from_offering, normalize_lesson_type
from app.planning.semester_planner import (
    build_course_snapshot,
    build_matrix_course_semester_index,
    build_workload_skip,
    get_course_credits,
    matrix_semesters_for_planning,
    normalize_course_id,
    partition_mandatory_by_matrix_semester,
    prerequisites_met,
    resolve_active_matrix_semester,
    select_courses_from_candidates,
)
from app.services.graduation_progress_calculator import round_credits
from app.planning.weekly_schedule import parse_time_range


def _option_slot(option: dict[str, Any]) -> dict[str, Any] | None:
    parsed = parse_time_range(str(option.get("timeRange") or "").replace("–", "-").replace("—", "-"))
    if not option.get("day") or parsed is None:
        return None
    start_minutes, end_minutes = parsed
    return {
        "day": str(option["day"]),
        "startMinutes": start_minutes,
        "endMinutes": end_minutes,
        "courseNumber": str(option.get("courseNumber") or ""),
        "eventId": str(option.get("eventId") or ""),
        "type": str(option.get("type") or "other"),
        "group": option.get("group"),
    }


def slots_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["day"] != right["day"]:
        return False
    return left["startMinutes"] < right["endMinutes"] and right["startMinutes"] < left["endMinutes"]


def _group_options_by_type(options: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for option in options:
        if option.get("incomplete"):
            continue
        lesson_type = normalize_lesson_type(str(option.get("type") or "other"))
        grouped.setdefault(lesson_type, []).append(option)
    return grouped


def _lesson_events_from_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "eventId": str(option["eventId"]),
            "type": str(option.get("type") or "other"),
            "group": option.get("group"),
        }
        for option in options
        if option.get("eventId")
    ]


def pick_lessons_for_course(
    options: list[dict[str, Any]],
    *,
    occupied_slots: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Pick one lesson per type with the fewest overlaps against occupied slots."""
    grouped = _group_options_by_type(options)
    if not grouped:
        return []

    type_keys = sorted(grouped.keys())
    combinations = itertools.product(*[grouped[key] for key in type_keys])
    best: list[dict[str, Any]] | None = None
    best_score: tuple[int, int] | None = None

    for combo in combinations:
        candidate_slots = [_option_slot(option) for option in combo]
        if any(slot is None for slot in candidate_slots):
            continue
        valid_slots = [slot for slot in candidate_slots if slot is not None]
        overlap_count = 0
        for slot in valid_slots:
            for occupied in occupied_slots:
                if slots_overlap(slot, occupied):
                    overlap_count += 1
                    break
        internal_conflicts = 0
        for left_index, left in enumerate(valid_slots):
            for right in valid_slots[left_index + 1 :]:
                if slots_overlap(left, right):
                    internal_conflicts += 1
        if internal_conflicts > 0:
            continue
        score = (overlap_count, sum(slot["startMinutes"] for slot in valid_slots))
        if best_score is None or score < best_score:
            best_score = score
            best = list(combo)

    if best is None:
        return None
    return _lesson_events_from_options(best)


def _exam_entries_for_course(
    offering: dict[str, Any] | None,
    *,
    course_number: str,
    course_title: str,
) -> list[dict[str, Any]]:
    return exams_from_offering(
        offering,
        course_number=course_number,
        course_name=course_title,
    )


def _offering_is_schedulable(
    offering: dict[str, Any] | None,
    *,
    course_number: str,
) -> tuple[bool, list[dict[str, Any]]]:
    if not offering:
        return False, []
    options = extract_lesson_options_from_offering(offering, course_number=course_number)
    return bool(options), options


def exams_conflict(existing: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> bool:
    existing_dates = {str(entry["date"]) for entry in existing if entry.get("date")}
    for entry in candidate:
        date_key = str(entry.get("date") or "")
        if date_key and date_key in existing_dates:
            return True
    return False


def _merge_selection_state(
    target: dict[str, Any],
    batch: dict[str, Any],
) -> None:
    """Sync scalar carry-over fields after an in-place batch selection."""
    target["totalCredits"] = batch["totalCredits"]
    target["occupiedSlots"] = batch["occupiedSlots"]
    target["examEntries"] = batch["examEntries"]
    target["localSatisfied"] = batch["localSatisfied"]
    target["plannedCourseNumbers"] = batch.get("plannedCourseNumbers") or set()


def _empty_selection_state(
    *,
    satisfied_course_ids: set[str],
) -> dict[str, Any]:
    return {
        "selectedCourses": [],
        "skippedDueToWorkload": [],
        "skippedDueToConflicts": [],
        "skippedDueToUnavailable": [],
        "totalCredits": 0.0,
        "occupiedSlots": [],
        "examEntries": [],
        "localSatisfied": set(satisfied_course_ids),
        "plannedCourseNumbers": set(),
    }


def build_selection_state_from_existing_planned(
    *,
    satisfied_course_ids: set[str],
    existing_planned: list[dict[str, Any]],
    offerings_by_number: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Seed conflict/credit state from courses already on the manual planner draft."""
    state = _empty_selection_state(satisfied_course_ids=set(satisfied_course_ids))

    for planned in existing_planned:
        if planned.get("isActive", True) is False:
            continue

        course_id = normalize_course_id(str(planned.get("courseId") or ""))
        if not course_id:
            continue

        course_number = str(planned.get("courseNumber") or "")
        course_title = str(planned.get("courseTitle") or "")
        credits = round_credits(float(planned.get("credits") or 0))

        state["localSatisfied"].add(course_id)
        if course_number:
            state["plannedCourseNumbers"].add(course_number)
        state["totalCredits"] = round_credits(state["totalCredits"] + credits)

        offering = offerings_by_number.get(course_number)
        selected_events = planned.get("selectedLessonEvents") or []
        if offering and selected_events:
            options = extract_lesson_options_from_offering(offering, course_number=course_number)
            selected_ids = {str(event.get("eventId") or "") for event in selected_events}
            for option in options:
                if str(option.get("eventId") or "") not in selected_ids:
                    continue
                slot = _option_slot({**option, "courseNumber": course_number})
                if slot:
                    state["occupiedSlots"].append(slot)

            state["examEntries"].extend(
                _exam_entries_for_course(
                    offering,
                    course_number=course_number,
                    course_title=course_title,
                )
            )

    return state


def select_conflict_aware_courses(
    *,
    mandatory_candidates: list[dict[str, Any]],
    elective_candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    max_credits_limit: float,
    offerings_by_number: dict[str, dict[str, Any]],
    academic_year: int,
    semester_code: int,
    initial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Greedy course selection that skips unavailable, conflicting, or blocked courses."""
    ordered = [
        *[
            (course, "mandatory", "Remaining mandatory course from degree semester matrix")
            for course in mandatory_candidates
        ],
        *[
            (course, "elective", "Elective selected after mandatory priorities")
            for course in elective_candidates
        ],
    ]

    state = initial_state or _empty_selection_state(satisfied_course_ids=satisfied_course_ids)
    selected_courses: list[dict[str, Any]] = state["selectedCourses"]
    skipped_due_to_workload: list[dict[str, Any]] = state["skippedDueToWorkload"]
    skipped_due_to_conflicts: list[dict[str, Any]] = state["skippedDueToConflicts"]
    skipped_due_to_unavailable: list[dict[str, Any]] = state["skippedDueToUnavailable"]
    occupied_slots: list[dict[str, Any]] = state["occupiedSlots"]
    exam_entries: list[dict[str, Any]] = state["examEntries"]
    total_credits = float(state["totalCredits"])
    local_satisfied = set(state["localSatisfied"])
    planned_course_numbers = set(state.get("plannedCourseNumbers") or set())

    for course, category, reason in ordered:
        course_id = normalize_course_id(course["_id"])
        course_number = str(course.get("number") or "")
        if course_id in local_satisfied or course_number in planned_course_numbers:
            continue
        if not prerequisites_met(course, local_satisfied):
            continue

        course_credits = get_course_credits(course)
        if total_credits + course_credits > max_credits_limit:
            skipped_due_to_workload.append(build_workload_skip(course, course_credits))
            continue

        course_title = str(course.get("title") or "")
        offering = offerings_by_number.get(course_number)
        schedulable, options = _offering_is_schedulable(offering, course_number=course_number)
        if not schedulable:
            skipped_due_to_unavailable.append(
                {
                    "courseId": course_id,
                    "courseNumber": course_number,
                    "courseTitle": course_title,
                    "reason": "Course is not offered with a published schedule in the selected semester",
                }
            )
            continue

        candidate_exams = _exam_entries_for_course(
            offering,
            course_number=course_number,
            course_title=course_title,
        )
        if exams_conflict(exam_entries, candidate_exams):
            skipped_due_to_conflicts.append(
                {
                    "courseId": course_id,
                    "courseNumber": course_number,
                    "courseTitle": course_title,
                    "reason": "Exam date conflicts with another selected course",
                }
            )
            continue

        selected_lessons = pick_lessons_for_course(options, occupied_slots=occupied_slots)
        if selected_lessons is None:
            skipped_due_to_conflicts.append(
                {
                    "courseId": course_id,
                    "courseNumber": course_number,
                    "courseTitle": course_title,
                    "reason": "No conflict-free lesson combination for this semester",
                }
            )
            continue

        snapshot = build_course_snapshot(course, category=category, reason=reason)
        snapshot["selectedLessonEvents"] = selected_lessons
        for option in options:
            if any(event["eventId"] == option.get("eventId") for event in selected_lessons):
                slot = _option_slot({**option, "courseNumber": course_number})
                if slot:
                    occupied_slots.append(slot)

        selected_courses.append(snapshot)
        exam_entries.extend(candidate_exams)
        local_satisfied.add(course_id)
        if course_number:
            planned_course_numbers.add(course_number)
        total_credits = round_credits(total_credits + course_credits)

    return {
        "selectedCourses": selected_courses,
        "skippedDueToWorkload": skipped_due_to_workload,
        "skippedDueToConflicts": skipped_due_to_conflicts,
        "skippedDueToUnavailable": skipped_due_to_unavailable,
        "totalCredits": total_credits,
        "occupiedSlots": occupied_slots,
        "examEntries": exam_entries,
        "localSatisfied": local_satisfied,
        "plannedCourseNumbers": planned_course_numbers,
    }


def select_progress_aware_courses(
    *,
    mandatory_candidates: list[dict[str, Any]],
    elective_candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    max_credits_limit: float,
    offerings_by_number: dict[str, dict[str, Any]],
    semester_matrix_documents: list[dict[str, Any]],
    courses_by_id: dict[str, dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
    academic_year: int,
    semester_code: int,
    initial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select courses semester-by-semester according to matrix progress, then electives."""
    state = (
        initial_state
        if initial_state is not None
        else _empty_selection_state(satisfied_course_ids=satisfied_course_ids)
    )
    active_semester = resolve_active_matrix_semester(
        semester_matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        completed_course_ids=satisfied_course_ids,
    )

    if semester_matrix_documents and active_semester is not None:
        matrix_index = build_matrix_course_semester_index(semester_matrix_documents)
        unmapped_mandatory, mandatory_by_semester = partition_mandatory_by_matrix_semester(
            mandatory_candidates,
            matrix_index,
        )
        semester_numbers = matrix_semesters_for_planning(
            mandatory_by_semester,
            active_semester=active_semester,
            completed_course_ids=satisfied_course_ids,
        )

        if unmapped_mandatory:
            batch = select_conflict_aware_courses(
                mandatory_candidates=unmapped_mandatory,
                elective_candidates=[],
                satisfied_course_ids=satisfied_course_ids,
                max_credits_limit=max_credits_limit,
                offerings_by_number=offerings_by_number,
                academic_year=academic_year,
                semester_code=semester_code,
                initial_state=state,
            )
            _merge_selection_state(state, batch)

        for semester_number in semester_numbers:
            if state["totalCredits"] >= max_credits_limit:
                break
            semester_mandatory = mandatory_by_semester.get(semester_number, [])
            if not semester_mandatory:
                continue
            batch = select_conflict_aware_courses(
                mandatory_candidates=semester_mandatory,
                elective_candidates=[],
                satisfied_course_ids=satisfied_course_ids,
                max_credits_limit=max_credits_limit,
                offerings_by_number=offerings_by_number,
                academic_year=academic_year,
                semester_code=semester_code,
                initial_state=state,
            )
            _merge_selection_state(state, batch)
    else:
        batch = select_conflict_aware_courses(
            mandatory_candidates=mandatory_candidates,
            elective_candidates=[],
            satisfied_course_ids=satisfied_course_ids,
            max_credits_limit=max_credits_limit,
            offerings_by_number=offerings_by_number,
            academic_year=academic_year,
            semester_code=semester_code,
            initial_state=state,
        )
        _merge_selection_state(state, batch)

    if state["totalCredits"] < max_credits_limit and elective_candidates:
        batch = select_conflict_aware_courses(
            mandatory_candidates=[],
            elective_candidates=elective_candidates,
            satisfied_course_ids=satisfied_course_ids,
            max_credits_limit=max_credits_limit,
            offerings_by_number=offerings_by_number,
            academic_year=academic_year,
            semester_code=semester_code,
            initial_state=state,
        )
        _merge_selection_state(state, batch)

    return {
        "selectedCourses": _dedupe_selected_courses(state["selectedCourses"]),
        "skippedDueToWorkload": state["skippedDueToWorkload"],
        "skippedDueToConflicts": state["skippedDueToConflicts"],
        "skippedDueToUnavailable": state["skippedDueToUnavailable"],
        "totalCredits": state["totalCredits"],
        "activeMatrixSemester": active_semester,
    }


def _dedupe_selected_courses(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    unique: list[dict[str, Any]] = []
    for course in courses:
        course_id = str(course.get("courseId") or "")
        if not course_id or course_id in seen_ids:
            continue
        seen_ids.add(course_id)
        unique.append(course)
    return unique


def optimize_schedule_for_planned_courses(
    planned_courses: list[dict[str, Any]],
    *,
    offerings_by_number: dict[str, dict[str, Any]],
    academic_year: int,
    semester_code: int,
) -> dict[str, Any]:
    """Assign lesson events across existing planned courses without conflicts."""
    occupied_slots: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for planned in planned_courses:
        if planned.get("isActive", True) is False:
            continue
        course_number = str(planned.get("courseNumber") or "")
        options = extract_lesson_options_from_offering(
            offerings_by_number.get(course_number),
            course_number=course_number,
        )
        if not options:
            skipped.append(
                {
                    "courseNumber": course_number,
                    "reason": "No published offering schedule for this semester",
                }
            )
            continue

        selected_lessons = pick_lessons_for_course(options, occupied_slots=occupied_slots)
        if selected_lessons is None:
            skipped.append(
                {
                    "courseNumber": course_number,
                    "reason": "No conflict-free lesson combination found",
                }
            )
            continue

        selections.append(
            {
                "courseNumber": course_number,
                "selectedLessonEvents": selected_lessons,
            }
        )
        for option in options:
            if any(event["eventId"] == option.get("eventId") for event in selected_lessons):
                slot = _option_slot({**option, "courseNumber": course_number})
                if slot:
                    occupied_slots.append(slot)

    exam_summary = build_exam_summary(
        [
            {
                **planned,
                "selectedLessonEvents": next(
                    (
                        item["selectedLessonEvents"]
                        for item in selections
                        if item["courseNumber"] == str(planned.get("courseNumber") or "")
                    ),
                    planned.get("selectedLessonEvents"),
                ),
            }
            for planned in planned_courses
            if planned.get("isActive", True) is not False
        ],
        offerings_by_number,
    )

    return {
        "selections": selections,
        "skippedCourses": skipped,
        "examSummary": exam_summary,
    }


def fallback_select_courses(
    *,
    mandatory_candidates: list[dict[str, Any]],
    elective_candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    max_credits_limit: float,
) -> dict[str, Any]:
    """Deterministic fallback when offerings are unavailable."""
    mandatory_selection = select_courses_from_candidates(
        candidates=mandatory_candidates,
        satisfied_course_ids=set(satisfied_course_ids),
        max_credits_limit=max_credits_limit,
        starting_credits=0,
        category="mandatory",
        default_reason="Remaining mandatory course from degree semester matrix",
    )
    selected = list(mandatory_selection["selectedCourses"])
    total_credits = mandatory_selection["totalCredits"]
    skipped_workload = list(mandatory_selection["skippedDueToWorkload"])

    if total_credits < max_credits_limit and elective_candidates:
        elective_selection = select_courses_from_candidates(
            candidates=elective_candidates,
            satisfied_course_ids=set(satisfied_course_ids),
            max_credits_limit=max_credits_limit,
            starting_credits=total_credits,
            category="elective",
            default_reason="Elective selected after mandatory priorities",
        )
        selected.extend(elective_selection["selectedCourses"])
        skipped_workload.extend(elective_selection["skippedDueToWorkload"])
        total_credits = elective_selection["totalCredits"]

    return {
        "selectedCourses": selected,
        "skippedDueToWorkload": skipped_workload,
        "skippedDueToConflicts": [],
        "totalCredits": total_credits,
    }
