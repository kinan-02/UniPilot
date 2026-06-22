import pytest

from app.config import Settings, get_settings
from app.db.catalog_bootstrap import ensure_development_catalog, seed_minimal_catalog


@pytest.mark.asyncio
async def test_ensure_development_catalog_seeds_when_empty(mongo_database) -> None:
    settings = Settings(
        environment="development",
        auto_seed_catalog=True,
        jwt_secret="test-secret",
    )
    seeded = await ensure_development_catalog(mongo_database, settings)
    assert seeded is True
    assert await mongo_database.degree_programs.count_documents({}) == 3
    assert await mongo_database.courses.count_documents({}) == 3
    resolved = get_settings()
    assert (
        await mongo_database[resolved.catalog_rules_collection].count_documents({})
        == 46
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
    assert await mongo_database.degree_programs.count_documents({}) == 3


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
