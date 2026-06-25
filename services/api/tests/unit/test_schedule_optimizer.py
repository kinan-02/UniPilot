"""Unit tests for conflict-aware schedule optimization."""

from __future__ import annotations

from app.planning.lesson_events import extract_lesson_options_from_offering
from app.planning.schedule_optimizer import (
    build_selection_state_from_existing_planned,
    exams_conflict,
    pick_lessons_for_course,
    select_conflict_aware_courses,
    select_progress_aware_courses,
    slots_overlap,
)


def _slot(day: str, start: int, end: int, course_number: str = "10001") -> dict:
    return {
        "day": day,
        "startMinutes": start,
        "endMinutes": end,
        "courseNumber": course_number,
        "eventId": f"{course_number}-{day}-{start}",
        "type": "lecture",
    }


def test_slots_overlap_detects_same_day_intersection() -> None:
    left = _slot("Sunday", 540, 660)
    right = _slot("Sunday", 600, 720)
    assert slots_overlap(left, right) is True
    assert slots_overlap(left, _slot("Monday", 600, 720)) is False


def test_pick_lessons_for_course_avoids_occupied_slot() -> None:
    options = [
        {
            "eventId": "lec-a",
            "type": "lecture",
            "day": "Sunday",
            "timeRange": "09:00-11:00",
            "courseNumber": "10001",
        },
        {
            "eventId": "lec-b",
            "type": "lecture",
            "day": "Monday",
            "timeRange": "09:00-11:00",
            "courseNumber": "10001",
        },
    ]

    selected = pick_lessons_for_course(options, occupied_slots=[_slot("Sunday", 540, 660)])
    assert selected is not None
    assert selected[0]["eventId"] == "lec-b"


def test_exams_conflict_detects_same_date() -> None:
    existing = [{"date": "2026-02-01", "courseNumber": "10001"}]
    candidate = [{"date": "2026-02-01", "courseNumber": "10002"}]
    assert exams_conflict(existing, candidate) is True
    assert exams_conflict(existing, [{"date": "2026-02-02", "courseNumber": "10002"}]) is False


def _offering(number: str, *, day: str = "Sunday", time: str = "10:30-12:30") -> dict:
    return {
        "courseNumber": number,
        "academicYear": 2025,
        "semesterCode": 202,
        "scheduleGroups": [{"day": day, "time": time, "type": "lecture"}],
    }


def _offering_with_exams(number: str, *, day: str = "Sunday", time: str = "10:30-12:30") -> dict:
    return {
        **_offering(number, day=day, time=time),
        "examDates": {"moedA": f"2025-06-{int(number[-2:]) % 28 + 1:02d} 09:00"},
    }


def test_build_selection_state_from_existing_planned_reserves_credits_and_slots() -> None:
    offering = _offering("10001", day="Sunday", time="08:30-10:30")
    options = extract_lesson_options_from_offering(offering, course_number="10001")
    assert options
    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "10001",
                "courseTitle": "Existing course",
                "credits": 4.0,
                "isActive": True,
                "selectedLessonEvents": [
                    {"eventId": options[0]["eventId"], "type": options[0]["type"]}
                ],
            }
        ],
        offerings_by_number={"10001": offering},
    )

    assert state["totalCredits"] == 4.0
    assert "existing-a" in state["localSatisfied"]
    assert len(state["occupiedSlots"]) == 1


def test_build_selection_state_skips_inactive_and_missing_course_id() -> None:
    offering = _offering("10001", day="Sunday", time="08:30-10:30")
    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "10001",
                "credits": 4.0,
                "isActive": False,
            },
            {
                "courseId": "",
                "courseNumber": "10002",
                "credits": 3.0,
                "isActive": True,
            },
            {
                "courseId": "existing-b",
                "courseNumber": "10001",
                "credits": 2.0,
                "isActive": True,
            },
        ],
        offerings_by_number={"10001": offering},
    )

    assert state["totalCredits"] == 2.0
    assert "existing-b" in state["localSatisfied"]
    assert "10001" in state["plannedCourseNumbers"]


def test_build_selection_state_ignores_unselected_lesson_options() -> None:
    offering = _offering_with_exams("10001", day="Sunday", time="08:30-10:30")

    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "10001",
                "credits": 4.0,
                "isActive": True,
                "selectedLessonEvents": [{"eventId": "non-matching-event", "type": "lecture"}],
            }
        ],
        offerings_by_number={"10001": offering},
    )

    assert state["totalCredits"] == 4.0
    assert state["occupiedSlots"] == []
    assert state["examEntries"]


def test_build_selection_state_seeds_exam_entries_without_lesson_selection() -> None:
    offering = _offering_with_exams("10001", day="Sunday", time="08:30-10:30")

    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "10001",
                "credits": 4.0,
                "isActive": True,
            }
        ],
        offerings_by_number={"10001": offering},
    )

    assert state["examEntries"]
    assert state["occupiedSlots"] == []


def test_build_selection_state_resolves_canonical_course_number_for_offerings() -> None:
    offering = _offering_with_exams("00940345", day="Sunday", time="08:30-10:30")
    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "0940345",
                "credits": 4.0,
                "isActive": True,
            }
        ],
        offerings_by_number={"00940345": offering},
    )

    assert "00940345" in state["plannedCourseNumbers"]
    assert state["examEntries"]


def test_select_conflict_aware_courses_skips_differently_padded_planned_numbers() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "00940345",
            "title": "Course A",
            "credits": 4,
            "prerequisites": [],
        }
    ]
    offerings = {"00940345": _offering("00940345", day="Sunday", time="10:30-12:30")}
    initial_state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "draft-a",
                "courseNumber": "0940345",
                "credits": 4.0,
                "isActive": True,
            }
        ],
        offerings_by_number=offerings,
    )

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=202,
        initial_state=initial_state,
    )

    assert result["selectedCourses"] == []
    assert result["totalCredits"] == 4.0


def test_build_selection_state_handles_empty_and_non_canonical_course_numbers() -> None:
    state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-empty",
                "courseNumber": "",
                "credits": 2.0,
                "isActive": True,
            },
            {
                "courseId": "existing-invalid",
                "courseNumber": "123456",
                "credits": 3.0,
                "isActive": True,
            },
        ],
        offerings_by_number={},
    )

    assert state["totalCredits"] == 5.0
    assert "existing-empty" in state["localSatisfied"]
    assert "existing-invalid" in state["localSatisfied"]
    assert state["examEntries"] == []


def test_select_conflict_aware_courses_uses_initial_state_for_credit_budget() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "10001",
            "title": "Course A",
            "credits": 5,
            "prerequisites": [],
        },
        {
            "_id": "course-b",
            "number": "10002",
            "title": "Course B",
            "credits": 5,
            "prerequisites": [],
        },
    ]
    offerings = {
        "10001": _offering("10001", day="Sunday", time="10:30-12:30"),
        "10002": _offering("10002", day="Monday", time="10:30-12:30"),
    }
    initial_state = build_selection_state_from_existing_planned(
        satisfied_course_ids=set(),
        existing_planned=[
            {
                "courseId": "existing-a",
                "courseNumber": "10001",
                "courseTitle": "Course A",
                "credits": 5.0,
                "isActive": True,
            }
        ],
        offerings_by_number=offerings,
    )

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=10,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=202,
        initial_state=initial_state,
    )

    assert len(result["selectedCourses"]) == 1
    assert result["selectedCourses"][0]["courseNumber"] == "10002"
    assert result["totalCredits"] == 10.0


def test_select_conflict_aware_courses_respects_max_credits() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "10001",
            "title": "Course A",
            "credits": 5,
            "prerequisites": [],
        },
        {
            "_id": "course-b",
            "number": "10002",
            "title": "Course B",
            "credits": 5,
            "prerequisites": [],
        },
    ]
    offerings = {
        "10001": _offering("10001", day="Sunday", time="10:30-12:30"),
        "10002": _offering("10002", day="Monday", time="10:30-12:30"),
    }

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=5,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=202,
    )

    assert len(result["selectedCourses"]) == 1
    assert result["totalCredits"] == 5
    assert len(result["skippedDueToWorkload"]) == 1


def test_select_conflict_aware_courses_skips_courses_without_term_offering() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "10001",
            "title": "Course A",
            "credits": 3,
            "prerequisites": [],
        }
    ]

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number={},
        academic_year=2025,
        semester_code=202,
    )

    assert result["selectedCourses"] == []
    assert len(result["skippedDueToUnavailable"]) == 1


def test_select_progress_aware_courses_prioritizes_first_matrix_semester() -> None:
    mandatory = [
        {"_id": "sem1", "number": "10001", "title": "Semester 1", "credits": 3, "prerequisites": []},
        {"_id": "sem2", "number": "10002", "title": "Semester 2", "credits": 3, "prerequisites": []},
    ]
    electives = [
        {"_id": "elec", "number": "20001", "title": "Elective", "credits": 3, "prerequisites": []},
    ]
    matrix_documents = [
        {
            "requirementGroupId": "prog:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "10001"}],
        },
        {
            "requirementGroupId": "prog:semester-2-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 2},
            "courseReferences": [{"courseNumber": "10002"}],
        },
    ]
    courses_by_number = {
        "10001": {
            "_id": "sem1",
            "courseNumber": "10001",
            "title": "Semester 1",
            "credits": 3,
            "prerequisites": [],
        },
        "10002": {
            "_id": "sem2",
            "courseNumber": "10002",
            "title": "Semester 2",
            "credits": 3,
            "prerequisites": [],
        },
        "20001": {
            "_id": "elec",
            "courseNumber": "20001",
            "title": "Elective",
            "credits": 3,
            "prerequisites": [],
        },
    }
    courses_by_id = {
        "sem1": mandatory[0],
        "sem2": mandatory[1],
        "elec": electives[0],
    }
    offerings = {
        "10001": _offering("10001", day="Sunday", time="08:30-10:30"),
        "10002": _offering("10002", day="Monday", time="08:30-10:30"),
        "20001": _offering("20001", day="Tuesday", time="08:30-10:30"),
    }

    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=electives,
        satisfied_course_ids=set(),
        max_credits_limit=6,
        offerings_by_number=offerings,
        semester_matrix_documents=matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        academic_year=2025,
        semester_code=202,
    )

    selected_numbers = [course["courseNumber"] for course in result["selectedCourses"]]
    assert "10001" in selected_numbers
    assert "10002" not in selected_numbers
    assert "20001" in selected_numbers
    assert result["activeMatrixSemester"] == 1


def test_select_progress_aware_courses_does_not_duplicate_across_batches() -> None:
    mandatory = [
        {"_id": "sem1", "number": "10001", "title": "Semester 1", "credits": 3, "prerequisites": []},
    ]
    electives = [
        {"_id": "sem1", "number": "10001", "title": "Semester 1", "credits": 3, "prerequisites": []},
    ]
    matrix_documents = [
        {
            "requirementGroupId": "prog:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "10001"}],
        },
    ]
    courses_by_number = {
        "10001": {
            "_id": "sem1",
            "courseNumber": "10001",
            "title": "Semester 1",
            "credits": 3,
            "prerequisites": [],
        },
    }
    courses_by_id = {"sem1": mandatory[0]}
    offerings = {"10001": _offering("10001")}

    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=electives,
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number=offerings,
        semester_matrix_documents=matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        academic_year=2025,
        semester_code=202,
    )

    assert len(result["selectedCourses"]) == 1
    assert result["selectedCourses"][0]["courseNumber"] == "10001"


def test_select_conflict_aware_courses_skips_impossible_lesson_combinations() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "10001",
            "title": "Course A",
            "credits": 3,
            "prerequisites": [],
        },
    ]
    offerings = {
        "10001": {
            "courseNumber": "10001",
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [
                {"day": "Sunday", "time": "08:30-10:30", "type": "lecture"},
                {"day": "Sunday", "time": "09:00-11:00", "type": "tutorial"},
            ],
        },
    }

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=201,
    )

    assert result["selectedCourses"] == []
    assert len(result["skippedDueToConflicts"]) == 1


def test_select_conflict_aware_courses_skips_exam_conflicts() -> None:
    mandatory = [
        {
            "_id": "course-a",
            "number": "10001",
            "title": "Course A",
            "credits": 3,
            "prerequisites": [],
        },
        {
            "_id": "course-b",
            "number": "10002",
            "title": "Course B",
            "credits": 3,
            "prerequisites": [],
        },
    ]
    offerings = {
        "10001": {
            **_offering("10001", day="Sunday", time="08:30-10:30"),
            "examDates": {"moedA": "2025-06-01 09:00"},
        },
        "10002": {
            **_offering("10002", day="Monday", time="08:30-10:30"),
            "examDates": {"moedA": "2025-06-01 10:00"},
        },
    }

    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=202,
    )

    assert len(result["selectedCourses"]) == 1
    assert len(result["skippedDueToConflicts"]) == 1


def test_optimize_schedule_for_planned_courses_assigns_non_overlapping_lessons() -> None:
    from app.planning.schedule_optimizer import optimize_schedule_for_planned_courses

    planned = [
        {"courseNumber": "10001", "isActive": True},
        {"courseNumber": "10002", "isActive": True},
    ]
    offerings = {
        "10001": _offering("10001", day="Sunday", time="08:30-10:30"),
        "10002": _offering("10002", day="Monday", time="08:30-10:30"),
    }

    result = optimize_schedule_for_planned_courses(
        planned,
        offerings_by_number=offerings,
        academic_year=2025,
        semester_code=202,
    )

    assert len(result["selections"]) == 2
    assert result["skippedCourses"] == []
    assert result["examSummary"] is not None


def test_select_progress_aware_courses_fills_later_matrix_semesters_for_veterans() -> None:
    mandatory = [
        {"_id": "sem4a", "number": "40001", "title": "Semester 4 A", "credits": 3, "prerequisites": []},
        {"_id": "sem4b", "number": "40002", "title": "Semester 4 B", "credits": 3, "prerequisites": []},
        {"_id": "sem5a", "number": "50001", "title": "Semester 5 A", "credits": 3, "prerequisites": []},
    ]
    matrix_documents = [
        {
            "requirementGroupId": "prog:semester-4-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 4},
            "courseReferences": [{"courseNumber": "40001"}, {"courseNumber": "40002"}],
        },
        {
            "requirementGroupId": "prog:semester-5-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 5},
            "courseReferences": [{"courseNumber": "50001"}],
        },
    ]
    courses_by_number = {
        "40001": {"_id": "sem4a", "courseNumber": "40001", "title": "Semester 4 A", "credits": 3, "prerequisites": []},
        "40002": {"_id": "sem4b", "courseNumber": "40002", "title": "Semester 4 B", "credits": 3, "prerequisites": []},
        "50001": {"_id": "sem5a", "courseNumber": "50001", "title": "Semester 5 A", "credits": 3, "prerequisites": []},
    }
    courses_by_id = {
        "sem4a": mandatory[0],
        "sem4b": mandatory[1],
        "sem5a": mandatory[2],
    }
    offerings = {
        "40001": _offering("40001", day="Sunday", time="08:30-10:30"),
        "40002": _offering("40002", day="Monday", time="08:30-10:30"),
        "50001": _offering("50001", day="Tuesday", time="08:30-10:30"),
    }
    completed_ids = {"done-1", "done-2", "done-3"}

    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=completed_ids,
        max_credits_limit=9,
        offerings_by_number=offerings,
        semester_matrix_documents=matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        academic_year=2025,
        semester_code=202,
    )

    selected_numbers = [course["courseNumber"] for course in result["selectedCourses"]]
    assert selected_numbers == ["40001", "40002", "50001"]
    assert result["activeMatrixSemester"] == 4
