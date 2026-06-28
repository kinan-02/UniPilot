"""Unit tests for transcript import commit service."""

import pytest

from app.schemas.transcript_import import CommitTranscriptCourseInput, CommitTranscriptImportRequest
from app.services.transcript_import_service import commit_transcript_import
from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)


@pytest.mark.asyncio
async def test_commit_transcript_import_skips_existing_duplicate(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    from app.repositories.completed_course_repository import create_completed_course

    user_id = "665f2b0f2a3f7b2a1a9a7c01"
    await create_completed_course(
        mongo_database,
        user_id,
        build_completed_course_payload(course["courseId"]),
    )

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2024-2",
                    grade=90,
                    creditsEarned=3,
                )
            ]
        ),
    )

    assert result["createdCount"] == 0
    assert result["skippedCount"] == 1


@pytest.mark.asyncio
async def test_commit_transcript_import_resolves_unpadded_course_number(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    user_id = "665f2b0f2a3f7b2a1a9a7c02"
    unpadded = course["courseNumber"][1:]

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=unpadded,
                    semesterCode="2024-2",
                    grade=90,
                    creditsEarned=3,
                )
            ]
        ),
    )

    assert result["createdCount"] == 1
    assert result["unresolvedCount"] == 0
