"""Fixtures for completed courses integration tests."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.repositories.completed_course_repository import create_completed_course

EXCLUDED_COURSE_NUMBER = "00960226"
KNOWN_COURSE_NUMBER = "00940345"


async def seed_production_course_fixture(database) -> dict[str, str]:
    settings = get_settings()
    insert_result = await database[settings.courses_collection].insert_one(
        {
            "productionKey": f"technion:course:{KNOWN_COURSE_NUMBER}",
            "institutionId": "technion",
            "courseNumber": KNOWN_COURSE_NUMBER,
            "titleHebrew": "מתמטיקה דיסקרטית",
            "title": "מתמטיקה דיסקרטית",
            "credits": 4.0,
            "faculty": "הפקולטה למדעי הנתונים וההחלטות",
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {"degreeRequirementsInferred": False},
            "status": "published",
        }
    )
    return {
        "courseId": str(insert_result.inserted_id),
        "courseNumber": KNOWN_COURSE_NUMBER,
    }


def build_completed_course_payload(course_id: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "courseId": course_id,
        "semesterCode": "2024-1",
        "grade": 82,
        "gradePoints": 82,
        "creditsEarned": 3,
        "attempt": 1,
    }
    payload.update(overrides)
    return payload


async def insert_official_completed_course_for_tests(
    database,
    user_id: str,
    record_data: dict[str, Any],
) -> dict[str, Any]:
    return await create_completed_course(
        database,
        user_id,
        {**record_data, "source": "official"},
    )
