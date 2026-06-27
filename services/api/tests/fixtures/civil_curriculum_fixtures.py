"""Fixtures for civil faculty curriculum integration tests."""

from __future__ import annotations

from app.db.e2e_civil_catalog_seed import (
    CIVIL_FACULTY_ID,
    CIVIL_KNOWN_COURSE,
    CIVIL_PROGRAM_CODE,
    CIVIL_TRACK_SLUG,
    seed_e2e_civil_catalog,
)


async def seed_civil_curriculum_fixtures(database) -> dict[str, str]:
    await seed_e2e_civil_catalog(database)

    from app.config import get_settings

    resolved = get_settings()
    program = await database[resolved.degree_programs_collection].find_one(
        {"programCode": CIVIL_PROGRAM_CODE},
    )
    assert program is not None
    program_id = str(program["_id"])

    course = await database[resolved.courses_collection].find_one({"courseNumber": CIVIL_KNOWN_COURSE})
    assert course is not None

    path_option = await database[resolved.catalog_path_options_collection].find_one(
        {"wikiSlug": CIVIL_TRACK_SLUG},
    )
    assert path_option is not None

    return {
        "programId": program_id,
        "programCode": CIVIL_PROGRAM_CODE,
        "trackSlug": CIVIL_TRACK_SLUG,
        "facultyId": CIVIL_FACULTY_ID,
        "knownCourseId": str(course["_id"]),
        "knownCourseNumber": CIVIL_KNOWN_COURSE,
        "pathOptionId": str(path_option["_id"]),
    }
