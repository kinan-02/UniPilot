"""Tests for Phase 12 guarded DDS production promotion."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.curation.catalog_policies import PRODUCTION_EXCLUDED_COURSE_NUMBERS
from app.importers.dds_catalog_staging_importer import PROMOTION_WRITE_COLLECTIONS
from app.main import run_promote_dds_to_production, run_rollback_dds_production_promotion
from app.promotion.dds_production_promoter import (
    ProductionPromotionError,
    run_dds_production_promotion,
    run_dds_production_rollback,
    validate_production_collections_for_promotion,
    _validate_document_safety,
)
from tests.test_dds_promotion_gate import (
    EXPECTED_PROGRAMS,
    HARD_GROUP_IDS,
    SEED_ADVISORY_GROUP_IDS,
    _seed_signed_off_promotion_staging,
)


def test_promote_refuses_without_dangerous_flag(mongo_database, monkeypatch) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    monkeypatch.setattr("app.main.check_mongo_connectivity", lambda: "connected")
    before = sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS)
    exit_code = run_promote_dds_to_production(False, False, True, None, None)
    after = sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS)
    assert exit_code == 2
    assert before == after == 0


def test_dry_run_writes_no_production_documents(mongo_database, tmp_path: Path) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    result = run_dds_production_promotion(
        mongo_database,
        dry_run=True,
        allow_warnings=True,
        json_path=tmp_path / "report.json",
        md_path=tmp_path / "report.md",
    )
    assert result.productionWritesPerformed is False
    assert result.promotionRun.status == "completed"
    assert sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS) == 0


def test_gate_is_rerun_before_promotion(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        dry_run=True,
        allow_warnings=True,
    )
    assert result.gate.checks
    assert result.gate.gateStatus in {"pass", "pass-with-warnings"}


def test_promotion_writes_expected_collections(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True
    assert result.promotionRun.status == "completed"
    assert mongo_database[settings.production_degree_programs_collection].count_documents({}) == 3
    assert (
        mongo_database[settings.production_degree_requirements_collection].count_documents({})
        == len(HARD_GROUP_IDS)
    )
    assert mongo_database[settings.production_catalog_rules_collection].count_documents({}) > 0
    unique_groups = len(
        mongo_database[settings.production_catalog_rules_collection].distinct("requirementGroupId")
    )
    assert unique_groups == mongo_database[settings.production_catalog_rules_collection].count_documents({})
    staged_courses = mongo_database[settings.staging_courses_collection].count_documents({})
    staged_offerings = mongo_database[settings.staging_course_offerings_collection].count_documents({})
    assert mongo_database[settings.production_courses_collection].count_documents({}) == staged_courses
    assert (
        mongo_database[settings.production_course_offerings_collection].count_documents({})
        == staged_offerings
    )
    assert mongo_database[settings.production_promotion_runs_collection].count_documents({}) == 1


def test_promotion_writes_advisory_requirement_group_record_type(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    record_types = mongo_database[settings.production_catalog_rules_collection].distinct("recordType")
    assert record_types == ["advisory_requirement_group"]


def test_idempotent_rerun_does_not_duplicate(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    first = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    counts_after_first = {
        name: mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS
    }
    second = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    counts_after_second = {
        name: mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS
    }
    assert first.productionWritesPerformed is True
    assert second.productionWritesPerformed is True
    assert counts_after_first == counts_after_second


def test_excluded_courses_are_skipped(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    for number in PRODUCTION_EXCLUDED_COURSE_NUMBERS[:2]:
        assert (
            mongo_database[settings.production_courses_collection].count_documents(
                {"courseNumber": number}
            )
            == 0
        )


def test_offerings_for_excluded_courses_are_skipped(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    excluded = PRODUCTION_EXCLUDED_COURSE_NUMBERS[0]
    mongo_database[settings.staging_course_offerings_collection].insert_one(
        {
            "stagingKey": f"technion:course-offering:{excluded}:2025:201",
            "courseNumber": excluded,
            "academicYear": 2025,
            "semesterCode": 201,
            "semesterName": "spring",
            "isStaging": True,
            "productionEligible": False,
        }
    )
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    assert (
        mongo_database[settings.production_course_offerings_collection].count_documents(
            {"courseNumber": excluded}
        )
        == 0
    )


def test_advisory_rules_are_non_enforced(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    enforced = mongo_database[settings.production_catalog_rules_collection].count_documents(
        {"enforceInGraduationProgress": True}
    )
    assert enforced == 0
    advisory = mongo_database[settings.production_catalog_rules_collection].count_documents(
        {"advisoryOnly": True}
    )
    assert advisory >= len(SEED_ADVISORY_GROUP_IDS)


def test_graduation_linked_pools_promoted_with_explicit_bucket_ids(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    ds_pool = mongo_database[settings.production_catalog_rules_collection].find_one(
        {"requirementGroupId": "009216-1-000:elective-ds-pool"}
    )
    faculty_pool = mongo_database[settings.production_catalog_rules_collection].find_one(
        {"requirementGroupId": "009216-1-000:elective-faculty-pool"}
    )
    assert ds_pool is not None
    ds_linked = ds_pool.get("linkedCreditBucketId") or ds_pool.get("sourceMetadata", {}).get(
        "linkedCreditBucketId"
    )
    assert ds_linked == "009216-1-000:elective-ds"
    assert faculty_pool is not None
    faculty_linked = faculty_pool.get("linkedCreditBucketId") or faculty_pool.get(
        "sourceMetadata", {}
    ).get("linkedCreditBucketId")
    assert faculty_linked == "009216-1-000:elective-faculty"


def test_hard_requirements_are_executable_only(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    for group_id in SEED_ADVISORY_GROUP_IDS:
        assert (
            mongo_database[settings.production_degree_requirements_collection].count_documents(
                {"requirementGroupId": group_id}
            )
            == 0
        )
    hard = mongo_database[settings.production_degree_requirements_collection].count_documents(
        {"ruleIsExecutable": True}
    )
    assert hard == len(HARD_GROUP_IDS)


def test_production_docs_exclude_staging_flags(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    sample = mongo_database[settings.production_courses_collection].find_one({})
    assert sample is not None
    assert "isStaging" not in sample
    assert "productionEligible" not in sample
    assert sample.get("promotionRunId")
    assert sample.get("promotedAt")


def test_no_degree_requirements_inferred_from_course_json() -> None:
    with pytest.raises(ProductionPromotionError):
        _validate_document_safety(
            {"metadata": {"degreeRequirementsInferred": True}},
            context="course",
        )


def test_conflicting_production_data_fails(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": "legacy-program",
            "programCode": "legacy",
            "catalogVersion": "2099-2099",
            "sourceName": "other-source",
        }
    )
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is False
    assert result.promotionRun.status == "failed"


def test_rollback_requires_dangerous_flag(mongo_database) -> None:
    summary = run_dds_production_rollback(
        mongo_database,
        promotion_run_id="missing",
        confirm_dangerous=False,
    )
    assert "error" in summary


def test_rollback_deletes_only_matching_promotion_run_id(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    result = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    run_id = result.promotionRun.promotionRunId
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": "foreign",
            "promotionRunId": "other-run",
            "programCode": "foreign",
        }
    )
    summary = run_dds_production_rollback(
        mongo_database,
        promotion_run_id=run_id,
        confirm_dangerous=True,
    )
    assert summary["status"] == "rolled_back"
    assert mongo_database[settings.production_degree_programs_collection].count_documents({}) == 1
    assert (
        mongo_database[settings.production_degree_programs_collection].find_one({})["promotionRunId"]
        == "other-run"
    )


def test_validate_production_collections_rejects_foreign_docs(mongo_database) -> None:
    settings = get_settings()
    mongo_database[settings.production_courses_collection].insert_one({"legacy": True})
    with pytest.raises(ProductionPromotionError):
        validate_production_collections_for_promotion(
            mongo_database,
            settings=settings,
            planned_keys_by_collection={settings.production_courses_collection: {"technion:course:1"}},
            catalog_version="2025-2026",
            source_name="technion-dds-catalog",
        )
