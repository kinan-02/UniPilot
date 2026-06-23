"""Unit tests for curriculum graph service orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.config import get_settings
from app.repositories.student_profile_repository import create_student_profile
from app.services import curriculum_graph_service as service
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures


@pytest.mark.asyncio
async def test_get_curriculum_graph_returns_degree_not_found(mongo_database):
    user_id = str(ObjectId())
    await mongo_database["student_profiles"].insert_one(
        {
            "userId": ObjectId(user_id),
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": ObjectId(),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
            "preferences": {},
            "revision": 1,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )

    result = await service.get_curriculum_graph_for_user(mongo_database, user_id)
    assert result["status"] == "degree_not_found"


@pytest.mark.asyncio
async def test_get_curriculum_graph_returns_curriculum_unavailable(mongo_database):
    settings = get_settings()
    program_insert = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": "technion-dds:program:009216-1-000:2025-2026",
            "institutionId": "technion",
            "programCode": "009216-1-000",
            "name": "IE",
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {"wikiPage": "track-data-information-engineering"},
            "status": "published",
        }
    )
    user_id = str(ObjectId())
    await mongo_database["student_profiles"].insert_one(
        {
            "userId": ObjectId(user_id),
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_insert.inserted_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
            "preferences": {},
            "revision": 1,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )

    result = await service.get_curriculum_graph_for_user(mongo_database, user_id)
    assert result["status"] == "curriculum_unavailable"


@pytest.mark.asyncio
async def test_load_base_graph_uses_cache_when_present(mongo_database):
    cached_graph = {"nodes": [], "edges": []}
    with patch(
        "app.services.curriculum_graph_service.get_cached_json",
        new=AsyncMock(return_value=cached_graph),
    ):
        result = await service._load_base_graph(
            mongo_database,
            track_slug="track-data-information-engineering",
            program_code="009216-1-000",
            catalog_year=2025,
            catalog_version="2025-2026",
        )
    assert result == cached_graph


@pytest.mark.asyncio
async def test_get_curriculum_graph_returns_track_not_configured(mongo_database):
    settings = get_settings()
    program_insert = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "institutionId": "technion",
            "programCode": "",
            "name": "Broken",
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {},
            "status": "published",
        }
    )
    user_id = str(ObjectId())
    await mongo_database["student_profiles"].insert_one(
        {
            "userId": ObjectId(user_id),
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_insert.inserted_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "custom-unconfigured-track"},
            "preferences": {},
            "revision": 1,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )

    result = await service.get_curriculum_graph_for_user(mongo_database, user_id)
    assert result["status"] == "track_not_configured"


@pytest.mark.asyncio
async def test_load_base_graph_merges_prefix_catalog_courses(mongo_database, monkeypatch):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)

    async def fake_list_semester_matrix(_db, _code):
        return [
            {
                "title": "Semester 1",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "courseReferences": [{"courseNumber": fixtures["courseANumber"]}],
                "advisoryOnly": True,
            }
        ]

    async def fake_list_pools(_db, _code):
        return [
            {
                "requirementGroupId": f"{fixtures['programId'].split()[0]}:elective-faculty-pool"
                if False
                else "009216-1-000:elective-faculty-pool",
                "ruleExpression": {
                    "type": "course_pool",
                    "operator": "min_credits",
                    "allowedPrefixes": ["0095"],
                },
                "courseReferences": [],
                "advisoryOnly": True,
            }
        ]

    prefix_only_course = {
        "_id": "665f2b0f2a3f7b2a1a9a7f99",
        "courseNumber": "00950101",
        "title": "Prefix-only course",
        "credits": 3.0,
    }

    async def fake_find_courses_by_numbers(_db, numbers):
        settings = get_settings()
        cursor = mongo_database[settings.courses_collection].find(
            {"courseNumber": fixtures["courseANumber"]}
        )
        return await cursor.to_list(length=10)

    async def fake_list_prefix_courses(_db, _prefixes, limit=500):
        return [prefix_only_course]

    monkeypatch.setattr(
        service.catalog_repository,
        "list_semester_matrix_rules_for_program",
        fake_list_semester_matrix,
    )
    monkeypatch.setattr(
        service.catalog_repository,
        "list_course_pools_for_program",
        fake_list_pools,
    )
    monkeypatch.setattr(
        service.catalog_repository,
        "find_courses_by_numbers",
        fake_find_courses_by_numbers,
    )
    monkeypatch.setattr(
        service.catalog_repository,
        "list_courses_by_number_prefixes",
        fake_list_prefix_courses,
    )
    monkeypatch.setattr(service, "get_cached_json", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "set_cached_json", AsyncMock())

    result = await service._load_base_graph(
        mongo_database,
        track_slug="track-data-information-engineering",
        program_code="009216-1-000",
        catalog_year=2025,
        catalog_version="2025-2026",
    )
    assert result is not None
    numbers = {node["courseNumber"] for node in result["nodes"]}
    assert fixtures["courseANumber"] in numbers


@pytest.mark.asyncio
async def test_get_curriculum_graph_success_with_fixtures(mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id = str(ObjectId())
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
            "preferences": {},
        },
    )

    result = await service.get_curriculum_graph_for_user(mongo_database, user_id)
    assert result["status"] == "ok"
    assert result["curriculumGraph"]["programCode"] == "009216-1-000"
