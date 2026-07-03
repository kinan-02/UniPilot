"""Unit tests for transcript import commit service."""

import pytest

from app.schemas.transcript_import import CommitTranscriptCourseInput, CommitTranscriptImportRequest
from app.services.transcript_import_service import commit_transcript_import
from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)


@pytest.mark.asyncio
async def test_commit_transcript_import_skips_exact_duplicate_row(mongo_database):
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
                    semesterCode="2024-1",
                    grade=82,
                    creditsEarned=3,
                )
            ]
        ),
    )

    assert result["createdCount"] == 0
    assert result["skippedCount"] == 1


@pytest.mark.asyncio
async def test_commit_transcript_import_stores_retake_in_new_semester_as_next_attempt(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    from app.repositories.completed_course_repository import create_completed_course

    user_id = "665f2b0f2a3f7b2a1a9a7c03"
    await create_completed_course(
        mongo_database,
        user_id,
        build_completed_course_payload(course["courseId"], semesterCode="2023-2", grade=40, creditsEarned=0),
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

    assert result["createdCount"] == 1
    assert result["created"][0]["attempt"] == 2


@pytest.mark.asyncio
async def test_commit_transcript_import_skips_same_semester_same_grade_when_credits_differ(
    mongo_database,
):
    course = await seed_production_course_fixture(mongo_database)
    from app.repositories.completed_course_repository import create_completed_course

    user_id = "665f2b0f2a3f7b2a1a9a7c04"
    await create_completed_course(
        mongo_database,
        user_id,
        build_completed_course_payload(course["courseId"], creditsEarned=3.0),
    )

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2024-1",
                    grade=82,
                    creditsEarned=3.5,
                )
            ]
        ),
    )

    assert result["createdCount"] == 0
    assert result["skippedCount"] == 1


@pytest.mark.asyncio
async def test_commit_transcript_import_stores_same_semester_pass_after_fail(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    from app.repositories.completed_course_repository import create_completed_course

    user_id = "665f2b0f2a3f7b2a1a9a7c05"
    await create_completed_course(
        mongo_database,
        user_id,
        build_completed_course_payload(
            course["courseId"],
            grade=40,
            creditsEarned=0,
        ),
    )

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2024-1",
                    grade=72,
                    creditsEarned=3,
                    attempt=2,
                )
            ]
        ),
    )

    assert result["createdCount"] == 1
    assert result["created"][0]["attempt"] == 2
    assert result["created"][0]["grade"] == 72


@pytest.mark.asyncio
async def test_commit_transcript_import_stores_pass_and_exemption_metadata(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    user_id = "665f2b0f2a3f7b2a1a9a7c06"

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2024-1",
                    grade=56,
                    creditsEarned=3,
                    warnings=["Recorded as pass grade"],
                )
            ]
        ),
    )

    assert result["createdCount"] == 1
    assert result["created"][0]["metadata"]["passGrade"] is True


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


@pytest.mark.asyncio
async def test_commit_transcript_import_replace_existing_removes_prior_pdf_rows(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    from app.repositories.completed_course_repository import create_completed_course

    user_id = "665f2b0f2a3f7b2a1a9a7c10"
    await create_completed_course(
        mongo_database,
        user_id,
        {
            **build_completed_course_payload(course["courseId"]),
            "source": "imported",
            "metadata": {
                "importSource": "transcript-pdf",
                "importedCourseNumber": course["courseNumber"],
            },
        },
    )

    result = await commit_transcript_import(
        mongo_database,
        user_id,
        CommitTranscriptImportRequest(
            replaceExisting=True,
            courses=[
                CommitTranscriptCourseInput(
                    courseNumber=course["courseNumber"],
                    semesterCode="2025-1",
                    grade=90,
                    creditsEarned=3,
                )
            ],
        ),
    )

    assert result["replacedCount"] == 1
    assert result["createdCount"] == 1
    assert result["skippedCount"] == 0
    assert result["created"][0]["metadata"]["importedCourseNumber"] == course["courseNumber"]
