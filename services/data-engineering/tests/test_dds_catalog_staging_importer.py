"""Tests for Phase 8 DDS curated catalog staging import."""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.importers.dds_catalog_staging_importer import (
    CatalogStagingImportError,
    assert_staging_collection_name,
    build_catalog_staging_plan,
    import_dds_catalog_to_staging,
    load_phase8_readiness,
    load_reviewed_catalog,
)

FIXTURE_CATALOG = Path(__file__).parent / "fixtures" / "dds_catalog_staging_import_catalog.json"
FIXTURE_READINESS_OK = Path(__file__).parent / "fixtures" / "dds_catalog_phase8_readiness_ok.json"
FIXTURE_READINESS_BLOCKED = (
    Path(__file__).parent / "fixtures" / "dds_catalog_phase8_readiness_blocked.json"
)


def test_assert_staging_collection_name_rejects_production() -> None:
    with pytest.raises(CatalogStagingImportError, match="production"):
        assert_staging_collection_name("degree_requirements")
    with pytest.raises(CatalogStagingImportError, match="production"):
        assert_staging_collection_name("catalog")


def test_build_plan_from_fixtures() -> None:
    document = load_reviewed_catalog(FIXTURE_CATALOG)
    readiness = load_phase8_readiness(FIXTURE_READINESS_OK)
    settings = get_settings()
    plan = build_catalog_staging_plan(
        document,
        readiness=readiness,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
        dry_run=True,
    )
    assert plan.summary.programsUpserted == 3
    assert plan.summary.requirementsUpserted == 3
    assert plan.summary.rulesUpserted == 2
    assert plan.summary.courseReferencesObserved == 2
    assert plan.summary.manualReviewRequiredItems >= 1


def test_dry_run_writes_nothing(mongo_database) -> None:
    settings = get_settings()
    summary = import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
        dry_run=True,
    )
    assert summary.dryRun is True
    assert mongo_database[settings.staging_degree_programs_collection].count_documents({}) == 0
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) == 0


def test_import_writes_staging_only(mongo_database) -> None:
    settings = get_settings()
    summary = import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
        dry_run=False,
    )
    assert summary.programsUpserted == 3
    assert summary.requirementsUpserted == 3
    assert summary.rulesUpserted == 2
    assert summary.ingestionRunId is not None
    assert mongo_database[settings.staging_degree_programs_collection].count_documents({}) == 3
    assert mongo_database[settings.staging_degree_requirements_collection].count_documents({}) == 3
    assert mongo_database[settings.staging_catalog_rules_collection].count_documents({}) == 2
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) == 1
    assert mongo_database.courses.count_documents({}) == 0
    assert mongo_database.degree_requirements.count_documents({}) == 0
    assert mongo_database.degrees.count_documents({}) == 0


def test_import_is_idempotent(mongo_database) -> None:
    settings = get_settings()
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    assert mongo_database[settings.staging_degree_programs_collection].count_documents({}) == 3
    assert mongo_database[settings.staging_degree_requirements_collection].count_documents({}) == 3
    assert mongo_database[settings.staging_catalog_rules_collection].count_documents({}) == 2
    assert mongo_database[settings.staging_ingestion_runs_collection].count_documents({}) == 2


def test_rejects_blocked_readiness(mongo_database) -> None:
    settings = get_settings()
    with pytest.raises(CatalogStagingImportError, match="blocked by readiness"):
        import_dds_catalog_to_staging(
            mongo_database,
            catalog_path=FIXTURE_CATALOG,
            readiness_path=FIXTURE_READINESS_BLOCKED,
            settings=settings,
        )


def test_preserves_manual_review_and_signoff_metadata(mongo_database) -> None:
    settings = get_settings()
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    program = mongo_database[settings.staging_degree_programs_collection].find_one(
        {"programCode": "009009-1-000"}
    )
    assert program is not None
    assert program["productionEligible"] is False
    assert program["requiresHumanSignoff"] is True
    assert program["signoffReview"]["reviewStatus"] == "ready-for-staging-with-review-flags"

    chain = mongo_database[settings.staging_degree_requirements_collection].find_one(
        {"requirementGroup.groupId": "009009-1-000:ie-statistics-elective-chain"}
    )
    assert chain is not None
    assert chain["requirementGroup"]["manualReviewRequired"] is True
    assert chain["treatsCoursesAsMandatory"] is False
    assert chain["requirementGroup"]["courseReferences"] == []


def test_preserves_missing_title_warning(mongo_database) -> None:
    settings = get_settings()
    import_dds_catalog_to_staging(
        mongo_database,
        catalog_path=FIXTURE_CATALOG,
        readiness_path=FIXTURE_READINESS_OK,
        settings=settings,
    )
    requirement = mongo_database[settings.staging_degree_requirements_collection].find_one(
        {"requirementGroup.groupId": "009216-1-000:semester-1-matrix"}
    )
    assert requirement is not None
    refs = requirement["requirementGroup"]["courseReferences"]
    missing = next(ref for ref in refs if ref["courseNumber"] == "01040031")
    assert missing["titleHint"] is None
    assert missing["manualReviewRequired"] is True


def test_rejects_production_ready_curation_status(mongo_database) -> None:
    payload = json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))
    payload["curationMetadata"]["curationStatus"] = "production-ready"
    bad_catalog = Path(__file__).parent / "fixtures" / "_tmp_production_ready.json"
    bad_catalog.write_text(json.dumps(payload), encoding="utf-8")
    try:
        with pytest.raises(CatalogStagingImportError, match="production-ready"):
            import_dds_catalog_to_staging(
                mongo_database,
                catalog_path=bad_catalog,
                readiness_path=FIXTURE_READINESS_OK,
                settings=get_settings(),
            )
    finally:
        bad_catalog.unlink(missing_ok=True)


def test_rejects_malformed_catalog_missing_signoff(mongo_database) -> None:
    payload = json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))
    payload.pop("signoffReview")
    bad_catalog = Path(__file__).parent / "fixtures" / "_tmp_no_signoff.json"
    bad_catalog.write_text(json.dumps(payload), encoding="utf-8")
    try:
        with pytest.raises(CatalogStagingImportError, match="signoffReview"):
            import_dds_catalog_to_staging(
                mongo_database,
                catalog_path=bad_catalog,
                readiness_path=FIXTURE_READINESS_OK,
                settings=get_settings(),
            )
    finally:
        bad_catalog.unlink(missing_ok=True)


def test_rejects_non_staging_collection_settings(mongo_database, monkeypatch) -> None:
    monkeypatch.setenv("STAGING_DEGREE_PROGRAMS_COLLECTION", "degree_programs")
    get_settings.cache_clear()
    settings = get_settings()
    try:
        with pytest.raises(CatalogStagingImportError, match="production"):
            import_dds_catalog_to_staging(
                mongo_database,
                catalog_path=FIXTURE_CATALOG,
                readiness_path=FIXTURE_READINESS_OK,
                settings=settings,
            )
    finally:
        get_settings.cache_clear()
