"""Additional unit tests for schedule_optimizer coverage."""

from __future__ import annotations

from app.planning.schedule_optimizer import (
    _dedupe_selected_courses,
    _group_options_by_type,
    _option_slot,
    fallback_select_courses,
    optimize_schedule_for_planned_courses,
    pick_lessons_for_course,
    select_conflict_aware_courses,
    select_progress_aware_courses,
)


def test_option_slot_returns_none_for_invalid_option() -> None:
    assert _option_slot({"day": "Sunday", "timeRange": "bad"}) is None
    assert _option_slot({"timeRange": "08:30-10:30"}) is None


def test_group_options_by_type_skips_incomplete() -> None:
    grouped = _group_options_by_type(
        [
            {"type": "lecture", "eventId": "a", "incomplete": True},
            {"type": "lecture", "eventId": "b", "incomplete": False},
        ]
    )
    assert len(grouped["lecture"]) == 1


def test_pick_lessons_returns_empty_list_when_no_grouped_options() -> None:
    assert pick_lessons_for_course([], occupied_slots=[]) == []


def test_select_conflict_aware_skips_when_prerequisites_not_met() -> None:
    mandatory = [
        {
            "_id": "course-b",
            "number": "10002",
            "title": "Course B",
            "credits": 3,
            "prerequisites": ["10001"],
        }
    ]
    result = select_conflict_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=12,
        offerings_by_number={
            "10002": {
                "courseNumber": "10002",
                "scheduleGroups": [{"day": "Monday", "time": "08:30-10:30", "type": "lecture"}],
            }
        },
        academic_year=2025,
        semester_code=201,
    )
    assert result["selectedCourses"] == []


def test_select_progress_aware_handles_unmapped_mandatory_and_electives() -> None:
    mandatory = [
        {"_id": "unmapped", "number": "90001", "title": "Unmapped", "credits": 3, "prerequisites": []},
        {"_id": "sem1", "number": "10001", "title": "Semester 1", "credits": 3, "prerequisites": []},
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
            "requirementGroupId": "prog:semester-3-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 3},
            "courseReferences": [],
        },
    ]
    courses_by_number = {
        "90001": {"_id": "unmapped", "courseNumber": "90001", "title": "Unmapped", "credits": 3},
        "10001": {"_id": "sem1", "courseNumber": "10001", "title": "Semester 1", "credits": 3},
        "20001": {"_id": "elec", "courseNumber": "20001", "title": "Elective", "credits": 3},
    }
    courses_by_id = {
        "unmapped": mandatory[0],
        "sem1": mandatory[1],
        "elec": electives[0],
    }
    offerings = {
        "90001": {
            "courseNumber": "90001",
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        },
        "10001": {
            "courseNumber": "10001",
            "scheduleGroups": [{"day": "Monday", "time": "08:30-10:30", "type": "lecture"}],
        },
        "20001": {
            "courseNumber": "20001",
            "scheduleGroups": [{"day": "Tuesday", "time": "08:30-10:30", "type": "lecture"}],
        },
    }

    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=electives,
        satisfied_course_ids=set(),
        max_credits_limit=9,
        offerings_by_number=offerings,
        semester_matrix_documents=matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        academic_year=2025,
        semester_code=201,
    )

    numbers = [course["courseNumber"] for course in result["selectedCourses"]]
    assert "90001" in numbers
    assert "10001" in numbers
    assert "20001" in numbers


def test_select_progress_aware_without_matrix_documents() -> None:
    mandatory = [
        {"_id": "course-a", "number": "10001", "title": "A", "credits": 3, "prerequisites": []},
    ]
    offerings = {
        "10001": {
            "courseNumber": "10001",
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        }
    }
    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids=set(),
        max_credits_limit=6,
        offerings_by_number=offerings,
        semester_matrix_documents=[],
        courses_by_id={"course-a": mandatory[0]},
        courses_by_number={"10001": {"_id": "course-a", "courseNumber": "10001", "credits": 3}},
        academic_year=2025,
        semester_code=201,
    )
    assert len(result["selectedCourses"]) == 1


def test_dedupe_selected_courses_skips_missing_ids() -> None:
    deduped = _dedupe_selected_courses(
        [
            {"courseId": "", "courseNumber": "10001"},
            {"courseId": "a", "courseNumber": "10002"},
            {"courseId": "a", "courseNumber": "10002"},
        ]
    )
    assert len(deduped) == 1


def test_optimize_schedule_skips_inactive_and_missing_offerings() -> None:
    planned = [
        {"courseNumber": "10001", "isActive": False},
        {"courseNumber": "10002", "isActive": True},
    ]
    result = optimize_schedule_for_planned_courses(
        planned,
        offerings_by_number={},
        academic_year=2025,
        semester_code=201,
    )
    assert result["selections"] == []
    assert len(result["skippedCourses"]) == 1


def test_optimize_schedule_skips_when_no_conflict_free_lessons() -> None:
    planned = [{"courseNumber": "10001", "isActive": True}]
    offering = {
        "courseNumber": "10001",
        "scheduleGroups": [
            {"day": "Sunday", "time": "08:30-10:30", "type": "lecture"},
            {"day": "Sunday", "time": "09:00-11:00", "type": "tutorial"},
        ],
    }
    result = optimize_schedule_for_planned_courses(
        planned,
        offerings_by_number={"10001": offering},
        academic_year=2025,
        semester_code=201,
    )
    assert result["selections"] == []
    assert result["skippedCourses"][0]["reason"] == "No conflict-free lesson combination found"


def test_fallback_select_courses_adds_electives_when_room_remains() -> None:
    mandatory = [
        {"_id": "m1", "number": "10001", "title": "M", "credits": 3, "prerequisites": []},
    ]
    electives = [
        {"_id": "e1", "number": "20001", "title": "E", "credits": 3, "prerequisites": []},
    ]
    result = fallback_select_courses(
        mandatory_candidates=mandatory,
        elective_candidates=electives,
        satisfied_course_ids=set(),
        max_credits_limit=9,
    )
    assert len(result["selectedCourses"]) == 2
    assert result["totalCredits"] == 6


def test_pick_lessons_skips_combinations_with_invalid_slots() -> None:
    options = [
        {
            "eventId": "lec-bad",
            "type": "lecture",
            "day": "Sunday",
            "timeRange": "invalid",
            "courseNumber": "10001",
        },
        {
            "eventId": "lec-good",
            "type": "lecture",
            "day": "Monday",
            "timeRange": "08:30-10:30",
            "courseNumber": "10001",
        },
        {
            "eventId": "tut-good",
            "type": "tutorial",
            "day": "Tuesday",
            "timeRange": "08:30-10:30",
            "courseNumber": "10001",
        },
    ]
    picked = pick_lessons_for_course(options, occupied_slots=[])
    assert picked is not None
    assert {event["eventId"] for event in picked} == {"lec-good", "tut-good"}


def test_select_progress_aware_breaks_when_max_credits_reached_mid_matrix() -> None:
    mandatory = [
        {"_id": "sem1a", "number": "10001", "title": "A", "credits": 3, "prerequisites": []},
        {"_id": "sem1b", "number": "10002", "title": "B", "credits": 3, "prerequisites": []},
        {"_id": "sem2a", "number": "20001", "title": "C", "credits": 3, "prerequisites": []},
    ]
    matrix_documents = [
        {
            "requirementGroupId": "prog:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "10001"}, {"courseNumber": "10002"}],
        },
        {
            "requirementGroupId": "prog:semester-2-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 2},
            "courseReferences": [{"courseNumber": "20001"}],
        },
    ]
    courses_by_number = {
        "10001": {"_id": "sem1a", "courseNumber": "10001", "credits": 3},
        "10002": {"_id": "sem1b", "courseNumber": "10002", "credits": 3},
        "20001": {"_id": "sem2a", "courseNumber": "20001", "credits": 3},
    }
    courses_by_id = {key: mandatory[idx] for idx, key in enumerate(["sem1a", "sem1b", "sem2a"])}
    offerings = {
        number: {
            "courseNumber": number,
            "scheduleGroups": [
                {"day": day, "time": "08:30-10:30", "type": "lecture"},
            ],
        }
        for number, day in [("10001", "Sunday"), ("10002", "Monday"), ("20001", "Tuesday")]
    }

    result = select_progress_aware_courses(
        mandatory_candidates=mandatory,
        elective_candidates=[],
        satisfied_course_ids={"done"},
        max_credits_limit=3,
        offerings_by_number=offerings,
        semester_matrix_documents=matrix_documents,
        courses_by_id=courses_by_id,
        courses_by_number=courses_by_number,
        academic_year=2025,
        semester_code=201,
    )

    assert len(result["selectedCourses"]) == 1
    assert result["selectedCourses"][0]["courseNumber"] == "10001"


def test_select_progress_aware_continues_when_matrix_semester_bucket_empty() -> None:
    from unittest.mock import patch

    mandatory = [
        {"_id": "sem1", "number": "10001", "title": "A", "credits": 3, "prerequisites": []},
    ]
    matrix_documents = [
        {
            "requirementGroupId": "prog:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "10001"}],
        },
    ]
    courses_by_number = {"10001": {"_id": "sem1", "courseNumber": "10001", "credits": 3}}
    courses_by_id = {"sem1": mandatory[0]}
    offerings = {
        "10001": {
            "courseNumber": "10001",
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        }
    }

    with patch(
        "app.planning.schedule_optimizer.matrix_semesters_for_planning",
        return_value=[1, 2],
    ):
        result = select_progress_aware_courses(
            mandatory_candidates=mandatory,
            elective_candidates=[],
            satisfied_course_ids={"done"},
            max_credits_limit=6,
            offerings_by_number=offerings,
            semester_matrix_documents=matrix_documents,
            courses_by_id=courses_by_id,
            courses_by_number=courses_by_number,
            academic_year=2025,
            semester_code=201,
        )

    assert len(result["selectedCourses"]) == 1
