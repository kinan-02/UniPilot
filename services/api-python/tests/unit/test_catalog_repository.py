"""Unit tests for catalog repository (read-only)."""

import pytest

from app.repositories import catalog_repository
from tests.fixtures.catalog_production_fixtures import KNOWN_COURSE, seed_catalog_production_fixtures


@pytest.mark.asyncio
async def test_repository_list_and_get_course(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)

    items, total = await catalog_repository.list_courses(mongo_database, limit=10, offset=0)
    assert total == 2
    assert any(item["courseNumber"] == KNOWN_COURSE for item in items)

    course = await catalog_repository.get_course_by_number(mongo_database, KNOWN_COURSE)
    assert course is not None
    assert course["courseNumber"] == KNOWN_COURSE
    assert "productionKey" not in course


@pytest.mark.asyncio
async def test_repository_never_writes_during_reads(mongo_database, monkeypatch):
    await seed_catalog_production_fixtures(mongo_database)

    async def fail_write(*_args, **_kwargs):
        raise AssertionError("catalog repository must not write during GET flows")

    monkeypatch.setattr(mongo_database.courses, "insert_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "update_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "replace_one", fail_write)
    monkeypatch.setattr(mongo_database.courses, "delete_one", fail_write)

    await catalog_repository.list_courses(mongo_database)
    await catalog_repository.get_course_by_number(mongo_database, KNOWN_COURSE)
    await catalog_repository.list_degree_programs(mongo_database)
