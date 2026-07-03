"""Unit tests for transcript review service."""

from __future__ import annotations

import pytest

from app.services.transcript_review_service import build_transcript_review, review_rows_for_commit
from tests.fixtures.completed_course_fixtures import seed_production_course_fixture


@pytest.mark.asyncio
async def test_build_transcript_review_marks_duplicate(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "confidence": 0.95,
                "title": "Discrete Math",
            }
        ],
        "warnings": [],
        "parseMetadata": {"extractor": "test"},
    }
    existing = [
        {
            "courseId": course["courseId"],
            "semesterCode": "2024-1",
            "grade": 85,
        }
    ]

    review = await build_transcript_review(
        mongo_database,
        parse_preview=parse_preview,
        completed_course_records=existing,
    )

    assert review.duplicateCount == 1
    assert review.rows[0].status == "duplicate"
    assert review_rows_for_commit(review) == []


@pytest.mark.asyncio
async def test_build_transcript_review_marks_matched(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2023-2",
                "grade": 90,
                "creditsEarned": 4,
                "confidence": 0.95,
            }
        ],
        "warnings": [],
        "parseMetadata": {},
    }

    review = await build_transcript_review(
        mongo_database,
        parse_preview=parse_preview,
        completed_course_records=[],
    )

    assert review.matchedCount == 1
    assert review.rows[0].status == "matched"
    assert len(review_rows_for_commit(review)) == 1
