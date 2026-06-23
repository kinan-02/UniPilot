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
    with pytest.raises(HTTPException) as exc_info:
        await validate_academic_path_for_profile(
            mongo_database,
            "665f2b0f2a3f7b2a1a9a7fff",
            {"trackSlug": "track-unknown"},
        )
    assert exc_info.value.status_code == 400
    assert "unknown" in exc_info.value.detail.lower()


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
