"""Unit tests for student profile catalog validation."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.student_profile_validation import (
    validate_academic_path_for_profile,
    validate_degree_id_for_profile,
)
from app.config import get_settings


@pytest.mark.asyncio
async def test_validate_degree_id_allows_existing_degree_program(mongo_database):
    from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await validate_degree_id_for_profile(mongo_database, fixtures["programId"])


@pytest.mark.asyncio
async def test_validate_degree_id_allows_none(mongo_database):
    await validate_degree_id_for_profile(mongo_database, None)


@pytest.mark.asyncio
async def test_validate_degree_id_allows_primary_path_option(mongo_database):
    from tests.fixtures.catalog_production_fixtures import seed_catalog_production_fixtures

    await seed_catalog_production_fixtures(mongo_database)
    graduate = await mongo_database[get_settings().catalog_path_options_collection].find_one(
        {"kind": "graduate_program", "selectableAsPrimary": True}
    )
    assert graduate is not None
    await validate_degree_id_for_profile(mongo_database, str(graduate["_id"]))


@pytest.mark.asyncio
async def test_validate_degree_id_rejects_missing_program(mongo_database):
    with pytest.raises(HTTPException) as exc_info:
        await validate_degree_id_for_profile(mongo_database, "665f2b0f2a3f7b2a1a9a7fff")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_academic_path_allows_empty_path(mongo_database):
    await validate_academic_path_for_profile(mongo_database, "665f2b0f2a3f7b2a1a9a7fff", None)
    await validate_academic_path_for_profile(mongo_database, "665f2b0f2a3f7b2a1a9a7fff", {})


@pytest.mark.asyncio
async def test_validate_academic_path_allows_missing_track_slug(mongo_database):
    await validate_academic_path_for_profile(
        mongo_database,
        "665f2b0f2a3f7b2a1a9a7fff",
        {"minors": []},
    )


@pytest.mark.asyncio
async def test_validate_academic_path_rejects_unknown_track_slug(mongo_database):
    from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            fixtures["programId"],
            {"trackSlug": "track-unknown"},
        )
    assert exc_info.value.status_code == 400
    assert "does not match" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_academic_path_requires_degree_when_track_set(mongo_database):
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            None,
            {"trackSlug": "track-data-information-engineering"},
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_academic_path_rejects_missing_degree_program(mongo_database):
    from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await mongo_database[get_settings().degree_programs_collection].delete_one(
        {"_id": __import__("bson").ObjectId(fixtures["programId"])}
    )
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            fixtures["programId"],
            {"trackSlug": "track-data-information-engineering"},
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_academic_path_rejects_mismatched_degree(mongo_database):
    from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            fixtures["programId"],
            {"trackSlug": "track-information-systems-engineering"},
        )
    assert exc_info.value.status_code == 400
    assert "does not match" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_academic_path_allows_primary_path_option_degree_id(mongo_database):
    from tests.fixtures.catalog_production_fixtures import seed_catalog_production_fixtures

    await seed_catalog_production_fixtures(mongo_database)
    graduate = await mongo_database[get_settings().catalog_path_options_collection].find_one(
        {"kind": "graduate_program", "selectableAsPrimary": True}
    )
    assert graduate is not None
    await validate_academic_path_for_profile(
        mongo_database,
        str(graduate["_id"]),
        {"trackSlug": "track-data-information-engineering"},
    )


@pytest.mark.asyncio
async def test_validate_academic_path_resolves_linked_degree_from_path_option(mongo_database):
    from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    path_insert = await mongo_database[get_settings().catalog_path_options_collection].insert_one(
        {
            "optionKey": "technion:dds:track-data-information-engineering",
            "institutionId": "technion",
            "facultyId": "faculty-dds",
            "wikiSlug": "track-data-information-engineering",
            "kind": "bsc_track",
            "name": "Data and Information Engineering",
            "selectableAsPrimary": True,
            "linkedDegreeProgramId": fixtures["programId"],
            "linkedProgramCode": "009216-1-000",
            "status": "published",
        }
    )
    await validate_academic_path_for_profile(
        mongo_database,
        str(path_insert.inserted_id),
        {"trackSlug": "track-data-information-engineering"},
    )


@pytest.mark.asyncio
async def test_validate_academic_path_rejects_program_without_track_metadata(mongo_database):
    program_insert = await mongo_database[get_settings().degree_programs_collection].insert_one(
        {
            "productionKey": "technion-test:program:999999-1-000:2025-2026",
            "institutionId": "technion",
            "programCode": "999999-1-000",
            "name": "Test program without wiki metadata",
            "totalCredits": 120.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {},
            "status": "published",
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            str(program_insert.inserted_id),
            {"trackSlug": "track-data-information-engineering"},
        )
    assert exc_info.value.status_code == 400
    assert "unknown track slug" in exc_info.value.detail.lower()
