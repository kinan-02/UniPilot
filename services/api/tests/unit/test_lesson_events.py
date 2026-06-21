"""Unit tests for lesson event utilities."""

from app.planning.lesson_events import (
    build_lesson_event_id,
    extract_lesson_options_from_offering,
    filter_groups_by_lesson_selection,
    migrate_legacy_selected_groups,
    normalize_lesson_type,
    sync_selected_groups_from_events,
    validate_lesson_selection,
)


def test_normalize_lesson_type_maps_hebrew_labels():
    assert normalize_lesson_type("הרצאה") == "lecture"
    assert normalize_lesson_type("תרגול") == "tutorial"
    assert normalize_lesson_type("מעבדה") == "lab"


def test_build_lesson_event_id_is_deterministic():
    event_id = build_lesson_event_id(
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
        lesson_type="lecture",
        group_label="10",
        day="Sunday",
        start_time="08:30",
        end_time="10:30",
        location="Taub 1",
    )
    assert event_id.startswith("02340114-2025-201-lecture-10-sunday-0830-1030")


def test_extract_lesson_options_from_offering():
    offering = {
        "courseNumber": "02340114",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [
            {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
            {"day": "Monday", "time": "10:30-11:30", "type": "tutorial", "group": "11"},
        ],
    }
    options = extract_lesson_options_from_offering(offering)
    assert len(options) == 2
    assert options[0]["type"] == "lecture"
    assert options[0]["group"] == "10"


def test_filter_groups_returns_empty_when_nothing_selected():
    groups = [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}]
    assert filter_groups_by_lesson_selection(groups) == []


def test_filter_groups_by_selected_lesson_events():
    offering = {
        "courseNumber": "02340114",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [
            {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
            {"day": "Tuesday", "time": "12:30-14:30", "type": "lecture", "group": "20"},
        ],
    }
    options = extract_lesson_options_from_offering(offering)
    selected = [{"eventId": options[0]["eventId"], "type": "lecture", "group": "10"}]
    filtered = filter_groups_by_lesson_selection(
        offering["scheduleGroups"],
        selected_lesson_events=selected,
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
    )
    assert len(filtered) == 1
    assert filtered[0]["group"] == "10"


def test_migrate_legacy_selected_groups_index():
    planned_course = {"selectedGroups": {"lecture": 0, "tutorial": None, "lab": None, "project": None}}
    schedule_groups = [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
        {"day": "Tuesday", "time": "12:30-14:30", "type": "lecture", "group": "20"},
    ]
    migrated = migrate_legacy_selected_groups(
        planned_course,
        schedule_groups,
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
    )
    assert len(migrated) == 1
    assert migrated[0]["type"] == "lecture"


def test_validate_lesson_selection_rejects_duplicates_and_unknown():
    options = extract_lesson_options_from_offering(
        {
            "courseNumber": "02340114",
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        }
    )
    errors = validate_lesson_selection(
        [
            {"eventId": options[0]["eventId"], "type": "lecture", "group": None},
            {"eventId": options[0]["eventId"], "type": "lecture", "group": None},
        ],
        options,
    )
    assert any("Duplicate" in error for error in errors)

    errors = validate_lesson_selection(
        [{"eventId": "missing-event", "type": "lecture", "group": None}],
        options,
    )
    assert any("not available" in error for error in errors)


def test_sync_selected_groups_from_events():
    groups = sync_selected_groups_from_events(
        [
            {"eventId": "a", "type": "lecture", "group": "10"},
            {"eventId": "b", "type": "tutorial", "group": "12"},
        ]
    )
    assert groups["lecture"] == ["10"]
    assert groups["tutorial"] == ["12"]
    assert groups["lab"] == []
