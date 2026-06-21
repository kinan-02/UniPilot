"""Unit tests for schedule_group_selection."""

from __future__ import annotations

from app.planning.schedule_group_selection import (
    available_group_options,
    filter_schedule_groups_by_selection,
)


def _make_groups():
    return [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
        {"day": "Monday", "time": "10:30-11:30", "type": "lecture", "group": "20"},
        {"day": "Tuesday", "time": "12:30-14:30", "type": "tutorial", "group": "30"},
    ]


# ---------------------------------------------------------------------------
# filter_schedule_groups_by_selection
# ---------------------------------------------------------------------------

def test_filter_schedule_groups_returns_empty_when_no_selection():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(groups, selected_groups=None)
    assert result == []


def test_filter_schedule_groups_returns_empty_for_empty_groups():
    result = filter_schedule_groups_by_selection([], selected_groups={"lecture": 0})
    assert result == []


def test_filter_schedule_groups_by_index_returns_correct_group():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups={"lecture": 0},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert len(result) == 1
    assert result[0]["group"] == "10"


def test_filter_schedule_groups_second_index():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups={"lecture": 1},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert len(result) == 1
    assert result[0]["group"] == "20"


def test_filter_schedule_groups_out_of_bounds_index():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups={"lecture": 99},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert result == []


def test_filter_schedule_groups_by_label_list():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups={"lecture": ["10"]},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert len(result) == 1
    assert result[0]["group"] == "10"


def test_filter_schedule_groups_by_lesson_events():
    from app.planning.lesson_events import extract_lesson_options_from_offering

    offering = {
        "courseNumber": "00940101",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": _make_groups(),
    }
    options = extract_lesson_options_from_offering(offering, course_number="00940101")
    lecture_option = next(o for o in options if o["type"] == "lecture")

    result = filter_schedule_groups_by_selection(
        _make_groups(),
        selected_groups=None,
        selected_lesson_events=[
            {"eventId": lecture_option["eventId"], "type": "lecture", "group": "10"}
        ],
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert len(result) == 1
    assert result[0]["group"] == "10"


def test_filter_schedule_groups_by_lesson_events_empty_event_ids():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups=None,
        selected_lesson_events=[{"type": "lecture"}],  # no eventId
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert result == []


def test_filter_schedule_groups_null_selected_groups_values():
    groups = _make_groups()
    result = filter_schedule_groups_by_selection(
        groups,
        selected_groups={"lecture": None, "tutorial": None},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert result == []


# ---------------------------------------------------------------------------
# available_group_options
# ---------------------------------------------------------------------------

def test_available_group_options_returns_options_per_slot_type():
    groups = _make_groups()
    result = available_group_options(groups)
    assert "lecture" in result
    assert "tutorial" in result
    assert len(result["lecture"]) == 2


def test_available_group_options_empty_for_empty_groups():
    result = available_group_options([])
    assert result == {}
