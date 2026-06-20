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
