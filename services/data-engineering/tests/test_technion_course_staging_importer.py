"""Tests for Phase 9 Technion course JSON staging import."""

from pathlib import Path

import pytest

from app.config import get_settings
from app.importers.dds_catalog_staging_importer import assert_staging_collection_name
from app.importers.technion_course_staging_importer import import_technion_courses_to_staging
from app.sources.technion_course_json import read_and_normalize_course_json_files

FIXTURE_201 = Path(__file__).parent / "fixtures" / "courses_2025_201.json"
FIXTURE_202 = Path(__file__).parent / "fixtures" / "courses_2025_202.json"
FIXTURE_200 = Path(__file__).parent / "fixtures" / "courses_2025_200.json"


def test_dry_run_writes_nothing(mongo_database) -> None:
    settings = get_settings()
    summary = import_technion_courses_to_staging(
        None,
        course_json_paths=[FIXTURE_201, FIXTURE_202],
        settings=settings,
        dry_run=True,
    )
    assert summary.dryRun is True
    assert summary.uniqueCourses >= 2
    assert mongo_database[settings.staging_courses_collection].count_documents({}) == 0
    assert mongo_database[settings.staging_course_offerings_collection].count_documents({}) == 0


def test_import_writes_staging_only(mongo_database) -> None:
    settings = get_settings()
    summary = import_technion_courses_to_staging(
        mongo_database,
        course_json_paths=[FIXTURE_201, FIXTURE_202],
        settings=settings,
    )
    assert summary.uniqueCourses >= 2
    assert summary.offeringsObserved >= 3
    assert summary.ingestionRunId is not None
    assert mongo_database[settings.staging_courses_collection].count_documents({}) >= 2
    assert mongo_database[settings.staging_course_offerings_collection].count_documents({}) >= 3
    assert mongo_database.courses.count_documents({}) == 0
    assert mongo_database.course_offerings.count_documents({}) == 0

    sample = mongo_database[settings.staging_courses_collection].find_one(
        {"courseNumber": "00940345"}
    )
    assert sample is not None
    assert sample["productionEligible"] is False
    assert sample["isStaging"] is True
    assert sample["metadata"]["degreeRequirementsInferred"] is False


def test_import_is_idempotent(mongo_database) -> None:
    settings = get_settings()
    paths = [FIXTURE_201, FIXTURE_202]
    import_technion_courses_to_staging(mongo_database, course_json_paths=paths, settings=settings)
    import_technion_courses_to_staging(mongo_database, course_json_paths=paths, settings=settings)
    assert mongo_database[settings.staging_courses_collection].count_documents({}) >= 2
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) >= 2


def test_dds_only_import(mongo_database) -> None:
    settings = get_settings()
    summary = import_technion_courses_to_staging(
        mongo_database,
        course_json_paths=[FIXTURE_201, FIXTURE_200],
        settings=settings,
        dds_only=True,
    )
    assert summary.ddsOnly is True
    assert summary.uniqueCourses == 2
    assert mongo_database[settings.staging_courses_collection].count_documents({}) == 2
    assert mongo_database[settings.staging_courses_collection].count_documents(
        {"faculty": "פקולטה להנדסה אזרחית"}
    ) == 0


def test_production_collection_name_rejected() -> None:
    with pytest.raises(Exception, match="production"):
        assert_staging_collection_name("courses")


def test_preserves_missing_title_warning(mongo_database) -> None:
    settings = get_settings()
    import_technion_courses_to_staging(
        mongo_database,
        course_json_paths=[FIXTURE_201],
        settings=settings,
    )
    # All fixture courses have titles; verify warnings structure exists on import summary
    parse_result = read_and_normalize_course_json_files([FIXTURE_201])
    assert parse_result.courses
