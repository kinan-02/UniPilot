from app.config import get_settings
from app.importers.staging_importer import import_records_to_staging
from app.sources.sample_data import (
    SAMPLE_COURSES,
    SAMPLE_DEGREE_REQUIREMENTS,
    SAMPLE_SOURCE_NAME,
    SAMPLE_SOURCE_TYPE,
)


def test_staging_importer_writes_only_to_staging_collections(mongo_database):
    settings = get_settings()

    finished_run = import_records_to_staging(
        mongo_database,
        source_name=SAMPLE_SOURCE_NAME,
        source_type=SAMPLE_SOURCE_TYPE,
        courses=SAMPLE_COURSES,
        degree_requirements=SAMPLE_DEGREE_REQUIREMENTS,
        settings=settings,
    )

    assert finished_run.status == "completed"
    assert finished_run.itemsValid == len(SAMPLE_COURSES) + len(SAMPLE_DEGREE_REQUIREMENTS)
    assert finished_run.itemsInvalid == 0

    assert mongo_database[settings.staging_courses_collection].count_documents({}) == len(
        SAMPLE_COURSES
    )
    assert mongo_database[settings.staging_degree_requirements_collection].count_documents(
        {}
    ) == len(SAMPLE_DEGREE_REQUIREMENTS)
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) == 1

    assert mongo_database.courses.count_documents({}) == 0
    assert mongo_database.degree_requirements.count_documents({}) == 0


def test_staging_importer_is_idempotent_for_same_sample_records(mongo_database):
    settings = get_settings()

    import_records_to_staging(
        mongo_database,
        source_name=SAMPLE_SOURCE_NAME,
        source_type=SAMPLE_SOURCE_TYPE,
        courses=SAMPLE_COURSES,
        degree_requirements=SAMPLE_DEGREE_REQUIREMENTS,
        settings=settings,
    )

    import_records_to_staging(
        mongo_database,
        source_name=SAMPLE_SOURCE_NAME,
        source_type=SAMPLE_SOURCE_TYPE,
        courses=SAMPLE_COURSES,
        degree_requirements=SAMPLE_DEGREE_REQUIREMENTS,
        settings=settings,
    )

    assert mongo_database[settings.staging_courses_collection].count_documents({}) == len(
        SAMPLE_COURSES
    )
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) == 2


def test_staging_importer_captures_invalid_records_without_crashing(mongo_database):
    settings = get_settings()
    invalid_course = {
        **SAMPLE_COURSES[0],
        "credits": 99,
    }

    finished_run = import_records_to_staging(
        mongo_database,
        source_name=SAMPLE_SOURCE_NAME,
        source_type=SAMPLE_SOURCE_TYPE,
        courses=[invalid_course],
        degree_requirements=[],
        settings=settings,
    )

    assert finished_run.status == "failed"
    assert finished_run.itemsValid == 0
    assert finished_run.itemsInvalid == 1
    assert finished_run.errors
    assert mongo_database[settings.staging_courses_collection].count_documents({}) == 0
