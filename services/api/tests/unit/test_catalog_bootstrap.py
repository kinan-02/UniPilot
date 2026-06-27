import pytest

from app.config import Settings, get_settings
from app.db.catalog_bootstrap import (
    DNE_ELECTIVE_DS_COURSE,
    ensure_development_catalog,
    seed_minimal_catalog,
)


@pytest.mark.asyncio
async def test_ensure_development_catalog_seeds_when_empty(mongo_database) -> None:
    settings = Settings(
        environment="development",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    seeded = await ensure_development_catalog(mongo_database, settings)
    assert seeded is True
    assert await mongo_database.degree_programs.count_documents({}) == 5
    assert await mongo_database.courses.count_documents({}) >= 5
    resolved = get_settings()
    assert (
        await mongo_database[resolved.catalog_rules_collection].count_documents({})
        == 59
    )


@pytest.mark.asyncio
async def test_ensure_development_catalog_skips_when_programs_exist(mongo_database) -> None:
    settings = Settings(
        environment="development",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    await seed_minimal_catalog(mongo_database, settings)
    seeded = await ensure_development_catalog(mongo_database, settings)
    assert seeded is False
    assert await mongo_database.degree_programs.count_documents({}) == 5


@pytest.mark.asyncio
async def test_ensure_development_catalog_skips_outside_development(mongo_database) -> None:
    settings = Settings(
        environment="production",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    seeded = await ensure_development_catalog(mongo_database, settings)
    assert seeded is False
    assert await mongo_database.degree_programs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_ensure_development_catalog_seeds_faculties_when_only_programs_exist(
    mongo_database,
) -> None:
    settings = Settings(
        environment="development",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    await seed_minimal_catalog(mongo_database, settings)
    resolved = get_settings()
    await mongo_database[resolved.catalog_faculties_collection].delete_many({})
    await mongo_database[resolved.catalog_path_options_collection].delete_many({})

    seeded = await ensure_development_catalog(mongo_database, settings)
    assert seeded is True
    assert await mongo_database[resolved.catalog_faculties_collection].count_documents({}) > 0
    assert await mongo_database[resolved.catalog_path_options_collection].count_documents({}) > 0


@pytest.mark.asyncio
async def test_seed_minimal_catalog_includes_e2e_cs_faculty_and_ds_elective_course(
    mongo_database,
) -> None:
    settings = Settings(
        environment="development",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    await seed_minimal_catalog(mongo_database, settings)
    resolved = get_settings()
    ds_pool = await mongo_database[resolved.catalog_rules_collection].find_one(
        {"requirementGroupId": "009216-1-000:elective-ds-pool"},
    )
    assert ds_pool is not None
    assert any(
        ref.get("courseNumber") in {DNE_ELECTIVE_DS_COURSE, "00960200"}
        for ref in (ds_pool.get("courseReferences") or [])
    )
    assert await mongo_database[resolved.catalog_faculties_collection].count_documents(
        {"facultyId": "faculty-computer-science"},
    ) == 1
    assert await mongo_database[resolved.catalog_faculties_collection].count_documents(
        {"facultyId": "faculty-civil-environmental-engineering"},
    ) == 1
