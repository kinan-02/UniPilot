"""Unit tests for catalog repository (read-only)."""

import pytest

from app.config import get_settings
from app.repositories import catalog_repository
from tests.fixtures.catalog_production_fixtures import KNOWN_COURSE, seed_catalog_production_fixtures


@pytest.mark.asyncio
async def test_find_degree_program_does_not_require_course_number(mongo_database):
    settings = get_settings()
    inserted = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "programCode": "009216-1-000",
            "name": "Test Program",
            "status": "published",
        }
    )
    program = await catalog_repository.find_degree_program_by_id(
        mongo_database,
        str(inserted.inserted_id),
    )
    assert program is not None
    assert program["programCode"] == "009216-1-000"


@pytest.mark.asyncio
async def test_repository_list_and_get_course(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)

    items, total = await catalog_repository.list_courses(mongo_database, limit=10, offset=0)
    assert total == 3
    assert any(item["courseNumber"] == KNOWN_COURSE for item in items)

    course = await catalog_repository.get_course_by_number(mongo_database, KNOWN_COURSE)
    assert course is not None
    assert course["courseNumber"] == KNOWN_COURSE
    assert "productionKey" not in course


@pytest.mark.asyncio
async def test_repository_prefers_advisory_requirement_group_over_legacy_catalog_rule(mongo_database):
    settings = get_settings()
    group_id = "009216-1-000:semester-1-matrix"
    await mongo_database[settings.catalog_rules_collection].insert_many(
        [
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "recordType": "catalog_rule",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [{"courseNumber": KNOWN_COURSE, "titleHint": "legacy"}],
                "status": "published",
            },
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "recordType": "advisory_requirement_group",
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [],
                "status": "published",
            },
        ]
    )

    rules = await catalog_repository.list_advisory_rules_for_program(mongo_database, "009216-1-000")
    semester_one = [rule for rule in rules if rule["requirementGroupId"] == group_id]
    assert len(semester_one) == 1


@pytest.mark.asyncio
async def test_repository_dedupes_duplicate_advisory_rules(mongo_database):
    settings = get_settings()
    group_id = "009216-1-000:semester-1-matrix"
    await mongo_database[settings.catalog_rules_collection].insert_many(
        [
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [],
                "status": "published",
            },
            {
                "programCode": "009216-1-000",
                "requirementGroupId": group_id,
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "courseReferences": [{"courseNumber": KNOWN_COURSE, "titleHint": "מתמטיקה דיסקרטית"}],
                "status": "published",
            },
        ]
    )

    rules = await catalog_repository.list_advisory_rules_for_program(mongo_database, "009216-1-000")
    semester_one = [rule for rule in rules if rule["requirementGroupId"] == group_id]
    assert len(semester_one) == 1
    assert semester_one[0]["courseReferences"][0]["courseNumber"] == KNOWN_COURSE

    matrices = await catalog_repository.list_semester_matrix_rules_for_program(
        mongo_database, "009216-1-000"
    )
    assert len(matrices) == 1
    assert matrices[0]["courseReferences"][0]["courseNumber"] == KNOWN_COURSE


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


@pytest.mark.asyncio
async def test_list_best_offerings_for_courses_batch(mongo_database):
    await seed_catalog_production_fixtures(mongo_database)

    best = await catalog_repository.list_best_offerings_for_courses(
        mongo_database,
        [KNOWN_COURSE],
        academic_year=2025,
        semester_code=201,
    )

    assert KNOWN_COURSE in best
    assert best[KNOWN_COURSE]["courseNumber"] == KNOWN_COURSE
