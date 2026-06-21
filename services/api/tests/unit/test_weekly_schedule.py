"""Unit tests for weekly schedule conflict detection."""

from app.planning.weekly_schedule import (
    build_weekly_schedule_payload,
    detect_schedule_conflicts,
    normalize_schedule_group,
    parse_time_range,
)


def test_parse_time_range_accepts_hyphen_variants():
    assert parse_time_range("10:30 - 12:30") == (630, 750)
    assert parse_time_range("10:30-12:30") == (630, 750)


def test_normalize_schedule_group_supports_hebrew_and_english_keys():
    assert normalize_schedule_group({"יום": "שלישי", "שעה": "10:30 - 12:30"}) == {
        "day": "שלישי",
        "timeRange": "10:30 - 12:30",
        "slotType": "",
    }
    assert normalize_schedule_group({"day": "Sunday", "time": "10:30-12:30", "type": "lecture"})[
        "day"
    ] == "Sunday"


def test_detect_schedule_conflicts_finds_overlap():
    entries = [
        {
            "courseNumber": "00940345",
            "courseTitle": "Course A",
            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
        },
        {
            "courseNumber": "00940411",
            "courseTitle": "Course B",
            "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30"}],
        },
    ]

    conflicts = detect_schedule_conflicts(entries)
    assert len(conflicts) == 1
    assert set(conflicts[0]["courseNumbers"]) == {"00940345", "00940411"}


def test_detect_schedule_conflicts_ignores_non_overlapping_days():
    entries = [
        {
            "courseNumber": "00940345",
            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
        },
        {
            "courseNumber": "00940411",
            "scheduleGroups": [{"day": "Monday", "time": "10:30-12:30"}],
        },
    ]

    assert detect_schedule_conflicts(entries) == []


def test_detect_schedule_conflicts_exact_overlap():
    entries = [
        {
            "courseNumber": "00940345",
            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
        },
        {
            "courseNumber": "00940411",
            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
        },
    ]
    assert len(detect_schedule_conflicts(entries)) == 1


def test_detect_schedule_conflicts_adjacent_classes_do_not_overlap():
    entries = [
        {
            "courseNumber": "00940345",
            "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
        },
        {
            "courseNumber": "00940411",
            "scheduleGroups": [{"day": "Sunday", "time": "12:30-14:30"}],
        },
    ]
    assert detect_schedule_conflicts(entries) == []


def test_detect_schedule_conflicts_partial_overlap():
    entries = [
        {
            "courseNumber": "00940345",
            "scheduleGroups": [{"day": "Tuesday", "time": "09:00-11:00"}],
        },
        {
            "courseNumber": "00940411",
            "scheduleGroups": [{"day": "Tuesday", "time": "10:00-12:00"}],
        },
    ]
    assert len(detect_schedule_conflicts(entries)) == 1


def test_build_weekly_schedule_payload_marks_conflicts_status():
    payload = build_weekly_schedule_payload(
        [
            {
                "courseNumber": "00940345",
                "courseTitle": "A",
                "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
            },
            {
                "courseNumber": "00940411",
                "courseTitle": "B",
                "scheduleGroups": [{"day": "Sunday", "time": "11:30-13:30"}],
            },
        ]
    )

    assert payload["status"] == "conflicts"
    assert len(payload["conflicts"]) == 1
    assert payload["weekView"][0]["day"] == "Sunday"


def test_build_weekly_schedule_payload_detects_custom_event_conflicts():
    payload = build_weekly_schedule_payload(
        [
            {
                "courseNumber": "00940345",
                "courseTitle": "A",
                "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
            },
        ],
        custom_events=[
            {
                "id": "gym",
                "title": "Gym",
                "day": "Sunday",
                "startTime": "11:00",
                "endTime": "12:00",
            }
        ],
    )

    assert payload["status"] == "conflicts"
    assert any("00940345" in (conflict.get("courseNumbers") or []) for conflict in payload["conflicts"])
    assert payload.get("customEvents")


def test_day_sort_key_returns_hebrew_rank():
    from app.planning.weekly_schedule import _day_sort_key

    assert _day_sort_key("ראשון") == (0, "0")
    assert _day_sort_key("שישי") == (0, "5")


def test_day_sort_key_returns_unknown_rank():
    from app.planning.weekly_schedule import _day_sort_key

    result = _day_sort_key("Zאאא")
    assert result[0] == 2


def test_parse_time_range_returns_none_when_end_before_start():
    from app.planning.weekly_schedule import parse_time_range

    assert parse_time_range("12:00-10:00") is None


def test_schedule_slots_skips_empty_day():
    from app.planning.weekly_schedule import _schedule_slots

    entry = {
        "courseNumber": "00940101",
        "courseTitle": "X",
        "scheduleGroups": [{"day": "", "time": "10:00-11:00"}],
    }
    assert _schedule_slots(entry) == []


def test_summarize_slot_types_adds_non_empty_types():
    from app.planning.weekly_schedule import summarize_slot_types

    groups = [
        {"type": "lecture"},
        {"type": ""},
        {"type": "lab"},
    ]
    result = summarize_slot_types(groups)
    assert "lecture" in result
    assert "lab" in result
    assert "" not in result


def test_build_weekly_schedule_payload_skips_custom_event_missing_fields():
    payload = build_weekly_schedule_payload(
        [],
        custom_events=[
            {"day": "", "startTime": "10:00", "endTime": "11:00", "title": "Bad"},
        ],
    )
    assert payload["status"] == "empty"


def test_detect_schedule_conflicts_deduplicates_same_pair():
    """Same pair reported multiple times should only appear once."""
    entries = [
        {
            "courseNumber": "00940345",
            "courseTitle": "A",
            "scheduleGroups": [
                {"day": "Sunday", "time": "10:00-12:00"},
                {"day": "Sunday", "time": "10:00-12:00"},
            ],
        },
        {
            "courseNumber": "00940411",
            "courseTitle": "B",
            "scheduleGroups": [{"day": "Sunday", "time": "10:00-12:00"}],
        },
    ]
    conflicts = detect_schedule_conflicts(entries)
    assert len(conflicts) == 1
