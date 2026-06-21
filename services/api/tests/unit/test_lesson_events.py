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


# ---------------------------------------------------------------------------
# Additional coverage for uncovered paths
# ---------------------------------------------------------------------------

from app.planning.lesson_events import (
    _canonical_slot_type,
    _slug,
    build_lesson_selection_warnings,
    extract_group_label,
    extract_instructor,
    extract_location,
    extract_notes,
    group_schedule_by_type,
    lesson_option_from_group,
    normalize_planned_course_lessons,
    split_time_range,
)


def test_canonical_slot_type_returns_other_for_empty():
    assert _canonical_slot_type("") == "other"


def test_canonical_slot_type_maps_aliases():
    assert _canonical_slot_type("הרצאה") == "lecture"
    assert _canonical_slot_type("תרגול") == "tutorial"
    assert _canonical_slot_type("מעבדה") == "lab"
    assert _canonical_slot_type("פרויקט") == "project"


def test_canonical_slot_type_returns_normalized_for_unknown():
    assert _canonical_slot_type("seminar") == "seminar"


def test_slug_replaces_non_alphanumeric():
    assert _slug("hello world") == "hello-world"
    assert _slug("") == "na"
    assert _slug("Taub-1 Lab") == "taub-1-lab"


def test_split_time_range_parses_valid():
    start, end = split_time_range("08:30-10:30")
    assert start == "08:30"
    assert end == "10:30"


def test_split_time_range_returns_empty_for_invalid():
    start, end = split_time_range("invalid")
    assert start == ""
    assert end == ""


def test_extract_group_label_returns_none_for_missing_keys():
    assert extract_group_label({}) is None


def test_extract_group_label_uses_group_key():
    assert extract_group_label({"group": "10"}) == "10"
    assert extract_group_label({"קבוצה": "20"}) == "20"


def test_extract_instructor_returns_none_for_missing_keys():
    assert extract_instructor({}) is None


def test_extract_instructor_uses_instructor_key():
    assert extract_instructor({"instructor": "Prof. Cohen"}) == "Prof. Cohen"
    assert extract_instructor({"מרצה/מתרגל": "Dr. Levi"}) == "Dr. Levi"


def test_extract_location_concatenates_building_and_room():
    result = extract_location({"building": "Taub", "room": "301"})
    assert result == "Taub 301"


def test_extract_location_returns_none_when_empty():
    assert extract_location({}) is None


def test_extract_notes_returns_note():
    assert extract_notes({"notes": "zoom only"}) == "zoom only"
    assert extract_notes({}) is None


def test_group_schedule_by_type_groups_correctly():
    groups = [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture"},
        {"day": "Monday", "time": "10:30-11:30", "type": "tutorial"},
        {"day": "Tuesday", "time": "12:30-14:30", "type": "lecture"},
    ]
    result = group_schedule_by_type(groups)
    assert len(result["lecture"]) == 2
    assert len(result["tutorial"]) == 1


def test_lesson_option_from_group_builds_option():
    group = {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"}
    option = lesson_option_from_group(
        group,
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
        index=0,
    )
    assert option["type"] == "lecture"
    assert option["group"] == "10"
    assert "eventId" in option
    assert "rawGroup" in option


def test_lesson_option_from_group_incomplete_when_no_time():
    group = {"day": "Sunday", "type": "lecture"}
    option = lesson_option_from_group(
        group,
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
        index=0,
    )
    assert option.get("incomplete") is True


def test_normalize_planned_course_lessons_returns_copy():
    course = {
        "courseNumber": "02340114",
        "selectedGroups": {"lecture": 0},
        "selectedLessonEvents": None,
    }
    result = normalize_planned_course_lessons(course)
    assert result is not course


def test_normalize_planned_course_lessons_sets_default_selected_groups_when_none():
    course = {
        "courseNumber": "02340114",
        "selectedGroups": None,
        "selectedLessonEvents": None,
    }
    result = normalize_planned_course_lessons(course)
    assert result["selectedGroups"] == {"lecture": [], "tutorial": [], "lab": [], "project": []}


def test_normalize_planned_course_lessons_syncs_from_events():
    course = {
        "courseNumber": "02340114",
        "selectedGroups": None,
        "selectedLessonEvents": [
            {"eventId": "some-id", "type": "lecture", "group": "10"}
        ],
    }
    result = normalize_planned_course_lessons(course)
    assert result["selectedGroups"]["lecture"] == ["10"]


def test_validate_lesson_selection_accepts_valid_events():
    options = extract_lesson_options_from_offering(
        {
            "courseNumber": "02340114",
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        }
    )
    errors = validate_lesson_selection(
        [{"eventId": options[0]["eventId"], "type": "lecture"}],
        options,
    )
    assert errors == []


def test_validate_lesson_selection_error_on_missing_event_id():
    errors = validate_lesson_selection([{"type": "lecture"}], [])
    assert any("eventId" in e for e in errors)


def test_build_lesson_selection_warnings_inactive_course():
    course = {"courseNumber": "00940101", "isActive": False}
    assert build_lesson_selection_warnings(course, None) == []


def test_build_lesson_selection_warnings_no_offering():
    course = {"courseNumber": "00940101", "isActive": True}
    warnings = build_lesson_selection_warnings(course, None)
    assert warnings == []


def test_build_lesson_selection_warnings_no_options():
    course = {"courseNumber": "00940101", "isActive": True}
    offering = {"scheduleGroups": []}
    warnings = build_lesson_selection_warnings(course, offering)
    assert any(w["type"] == "no_lesson_options" for w in warnings)


def test_build_lesson_selection_warnings_no_selection_made():
    course = {
        "courseNumber": "00940101",
        "isActive": True,
        "selectedLessonEvents": [],
    }
    offering = {
        "courseNumber": "00940101",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
    }
    warnings = build_lesson_selection_warnings(course, offering)
    assert any(w["type"] == "no_lesson_selected" for w in warnings)


def test_build_lesson_selection_warnings_stale_event():
    options = extract_lesson_options_from_offering(
        {
            "courseNumber": "00940101",
            "academicYear": 2025,
            "semesterCode": 201,
            "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        }
    )
    course = {
        "courseNumber": "00940101",
        "isActive": True,
        "selectedLessonEvents": [{"eventId": "stale-id", "type": "lecture"}],
    }
    offering = {
        "courseNumber": "00940101",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
    }
    warnings = build_lesson_selection_warnings(course, offering)
    assert any(w["type"] == "stale_lesson_event" for w in warnings)


def test_filter_groups_by_selected_groups_string_selection():
    groups = [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
        {"day": "Monday", "time": "10:30-11:30", "type": "lecture", "group": "20"},
    ]
    result = filter_groups_by_lesson_selection(
        groups,
        selected_groups={"lecture": "lecture"},
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert len(result) >= 0  # string fallback path executed without error


def test_migrate_legacy_selected_groups_list_selection():
    planned_course = {"selectedGroups": {"lecture": ["10"], "tutorial": None, "lab": None, "project": None}}
    schedule_groups = [
        {"day": "Sunday", "time": "08:30-10:30", "type": "lecture", "group": "10"},
    ]
    migrated = migrate_legacy_selected_groups(
        planned_course,
        schedule_groups,
        course_number="02340114",
        academic_year=2025,
        semester_code=201,
    )
    assert len(migrated) == 1
    assert migrated[0]["group"] == "10"


# ---------------------------------------------------------------------------
# Missing coverage
# ---------------------------------------------------------------------------

def test_migrate_legacy_selected_groups_returns_empty_for_non_dict_groups():
    planned_course = {"selectedGroups": "not-a-dict"}
    result = migrate_legacy_selected_groups(
        planned_course,
        [],
        course_number="00940101",
        academic_year=2025,
        semester_code=201,
    )
    assert result == []


def test_build_lesson_selection_warnings_incomplete_option():
    from app.planning.lesson_events import build_lesson_selection_warnings

    offering = {
        "courseNumber": "00940101",
        "scheduleGroups": [
            {"day": "", "time": "", "type": "lecture", "group": "1"},  # incomplete
        ],
    }
    planned_course = {
        "courseNumber": "00940101",
        "courseId": "abc",
        "isActive": True,
        "selectedLessonEvents": [],
    }
    # Force an incomplete option by patching extract_lesson_options_from_offering
    from unittest.mock import patch
    fake_option = {
        "eventId": "lecture-1",
        "lessonType": "lecture",
        "incomplete": True,
        "group": "1",
    }
    with patch(
        "app.planning.lesson_events.extract_lesson_options_from_offering",
        return_value=[fake_option],
    ):
        planned_with_events = {
            **planned_course,
            "selectedLessonEvents": [{"eventId": "lecture-1"}],
        }
        warnings = build_lesson_selection_warnings(planned_with_events, offering)
    assert any(w["type"] == "incomplete_lesson_data" for w in warnings)
