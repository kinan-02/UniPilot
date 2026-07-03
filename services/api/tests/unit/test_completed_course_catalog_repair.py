"""Unit tests for stale catalog link repair on completed courses."""

import pytest
from bson import ObjectId

from app.repositories.completed_course_repository import create_completed_course
from app.services.completed_course_catalog_repair import repair_stale_completed_course_catalog_links
from tests.fixtures.completed_course_fixtures import build_completed_course_payload, seed_production_course_fixture


@pytest.mark.asyncio
async def test_repair_stale_completed_course_catalog_links_updates_course_id(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    user_id = "665f2b0f2a3f7b2a1a9a7c11"
    stale_id = str(ObjectId())

    record = await create_completed_course(
        mongo_database,
        user_id,
        {
            **build_completed_course_payload(stale_id),
            "source": "imported",
            "metadata": {
                "importedCourseNumber": course["courseNumber"],
                "importedTitle": "Sample course",
            },
        },
    )

    repaired_records, catalog_by_id = await repair_stale_completed_course_catalog_links(
        mongo_database,
        [record],
        {},
    )

    assert str(repaired_records[0]["courseId"]) == course["courseId"]
    assert course["courseId"] in catalog_by_id
