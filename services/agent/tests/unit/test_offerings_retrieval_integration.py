"""Integration tests for offerings retrieval with Mongo fixtures."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.offerings_retriever import retrieve_offerings_context


@pytest.fixture
async def offerings_fixtures(mongo_database):
    settings = get_settings()
    await mongo_database[settings.course_offerings_collection].insert_many(
        [
            {
                "productionKey": "technion:course-offering:00940345:2025:201",
                "courseNumber": "00940345",
                "academicYear": 2025,
                "semesterCode": 201,
                "scheduleGroups": [{"day": "Sunday", "time": "08:30-10:30", "type": "lecture"}],
                "status": "published",
            },
            {
                "productionKey": "technion:course-offering:00940345:2024:201",
                "courseNumber": "00940345",
                "academicYear": 2024,
                "semesterCode": 201,
                "scheduleGroups": [{"day": "Monday", "time": "08:30-10:30", "type": "lecture"}],
                "status": "published",
            },
            {
                "productionKey": "technion:course-offering:00940224:2025:200",
                "courseNumber": "00940224",
                "academicYear": 2025,
                "semesterCode": 200,
                "scheduleGroups": [{"day": "Tuesday", "time": "10:30-12:30", "type": "lecture"}],
                "status": "published",
            },
        ]
    )
    yield mongo_database


@pytest.mark.asyncio
async def test_exact_offering_semester_lookup(offerings_fixtures):
    academic, records = await retrieve_offerings_context(
        offerings_fixtures,
        queries=[{"courseNumber": "00940345", "semester": "2025-2"}],
        entities={"courseNumber": "00940345", "targetSemesterCode": "2025-2"},
    )
    assert academic.get("offering") is not None
    assert academic["offering"]["courseNumber"] == "00940345"
    source_ids = [record.source_id for record in records]
    assert "offering:2025-2:00940345" in source_ids


@pytest.mark.asyncio
async def test_wrong_semester_avoidance_returns_different_source(offerings_fixtures):
    academic, records = await retrieve_offerings_context(
        offerings_fixtures,
        queries=[{"courseNumber": "00940345", "semester": "2025-2"}],
        entities={"courseNumber": "00940345", "targetSemesterCode": "2025-2"},
    )
    source_ids = [record.source_id for record in records]
    assert "offering:2024-2:00940345" not in source_ids
    assert "offering:2025-2:00940345" in source_ids


@pytest.mark.asyncio
async def test_offering_lookup_without_semester_lists_course(offerings_fixtures):
    academic, records = await retrieve_offerings_context(
        offerings_fixtures,
        queries=[{"courseNumber": "00940224"}],
        entities={"courseNumber": "00940224"},
    )
    assert academic.get("offerings")
    assert len(academic["offerings"]) >= 1


@pytest.mark.asyncio
async def test_offering_lookup_missing_course_returns_empty(offerings_fixtures):
    academic, records = await retrieve_offerings_context(
        offerings_fixtures,
        queries=[{"courseNumber": "00000000", "semester": "2025-2"}],
        entities={"courseNumber": "00000000", "targetSemesterCode": "2025-2"},
    )
    assert academic.get("offering") is None
    assert records == []
