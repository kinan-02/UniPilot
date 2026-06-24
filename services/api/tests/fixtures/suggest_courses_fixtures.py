"""Offerings fixtures for semester plan suggestion integration tests."""

from __future__ import annotations

from typing import Any

from app.config import get_settings

DEFAULT_OFFERINGS: list[dict[str, Any]] = [
    {
        "productionKey": "technion:course-offering:00940345:2025:201",
        "courseNumber": "00940345",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
        "examDates": {"moedA": "2025-06-01 09:00", "moedB": "2025-07-01 09:00"},
        "status": "published",
    },
    {
        "productionKey": "technion:course-offering:01040031:2025:201",
        "courseNumber": "01040031",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Monday", "time": "08:30-10:30", "type": "lecture"}],
        "examDates": {"moedA": "2025-06-02 09:00", "moedB": "2025-07-02 09:00"},
        "status": "published",
    },
    {
        "productionKey": "technion:course-offering:00940219:2025:201",
        "courseNumber": "00940219",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Tuesday", "time": "08:30-10:30", "type": "lecture"}],
        "examDates": {"moedA": "2025-06-03 09:00", "moedB": "2025-07-03 09:00"},
        "status": "published",
    },
    {
        "productionKey": "technion:course-offering:00940411:2025:201",
        "courseNumber": "00940411",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Wednesday", "time": "08:30-10:30", "type": "lecture"}],
        "examDates": {"moedA": "2025-06-04 09:00", "moedB": "2025-07-04 09:00"},
        "status": "published",
    },
    {
        "productionKey": "technion:course-offering:09400101:2025:201",
        "courseNumber": "09400101",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Thursday", "time": "08:30-10:30", "type": "lecture"}],
        "examDates": {"moedA": "2025-06-05 09:00", "moedB": "2025-07-05 09:00"},
        "status": "published",
    },
]


async def seed_suggest_courses_offerings(database) -> None:
    """Seed non-conflicting spring offerings for graduation-progress fixture courses."""
    settings = get_settings()
    await database[settings.course_offerings_collection].insert_many(DEFAULT_OFFERINGS)


def offering_with_schedule_conflict(course_number: str) -> dict[str, Any]:
    """Return an offering that overlaps Sunday 08:30-10:30 with discrete math."""
    return {
        "productionKey": f"technion:course-offering:{course_number}:2025:201:conflict",
        "courseNumber": course_number,
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{"day": "Sunday", "time": "09:00-11:00", "type": "lecture"}],
        "examDates": {"moedA": "2025-08-01 09:00"},
        "status": "published",
    }
