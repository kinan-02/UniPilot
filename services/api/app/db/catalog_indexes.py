"""MongoDB indexes for catalog read performance."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings


async def ensure_catalog_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()

    courses = database[settings.courses_collection]
    await courses.create_index(
        [("status", 1), ("courseNumber", 1)],
        name="courses_status_course_number",
    )
    await courses.create_index(
        [("status", 1), ("faculty", 1)],
        name="courses_status_faculty",
    )

    offerings = database[settings.course_offerings_collection]
    await offerings.create_index(
        [("status", 1), ("courseNumber", 1), ("semesterCode", 1), ("academicYear", 1)],
        name="offerings_status_course_term",
    )
    await offerings.create_index(
        [("status", 1), ("semesterCode", 1), ("academicYear", 1)],
        name="offerings_status_term",
    )

    programs = database[settings.degree_programs_collection]
    await programs.create_index(
        [("status", 1), ("programCode", 1)],
        name="degree_programs_status_code",
    )
