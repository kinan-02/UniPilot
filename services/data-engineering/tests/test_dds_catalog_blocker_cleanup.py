"""Tests for Phase 10.5 DDS staging blocker cleanup."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.curation.dds_catalog_blocker_cleanup import (
    COGNITION_TRACK_GROUP_ID,
    MISSING_REFERENCE_CLASSIFICATIONS,
    apply_blocker_cleanup,
    build_phase8_readiness_check,
    run_blocker_cleanup,
)
from app.quality.dds_staging_quality import build_dds_staging_quality_report
from app.utils.course_numbers import normalize_course_number

FIXTURE_CATALOG = Path(__file__).parent / "fixtures" / "dds_catalog_blocker_cleanup_fixture.json"


@pytest.fixture
def cleanup_catalog() -> dict:
    return json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8"))


def test_normalize_course_number_preserves_01040030() -> None:
    assert normalize_course_number("01040030") == "01040030"


def test_ocr_suspect_classification_present() -> None:
    assert MISSING_REFERENCE_CLASSIFICATIONS["00906292"] == "duplicate-ocr-artifact-removed"
    assert MISSING_REFERENCE_CLASSIFICATIONS["02300401"] == "likely-ocr-artifact-removed"


def test_removes_duplicate_ocr_artifact_without_correction(cleanup_catalog: dict) -> None:
    result = apply_blocker_cleanup(cleanup_catalog, course_json_paths=[])
    removed = [change for change in result.changes if change.action == "remove"]
    assert any(change.courseNumber == "00906292" for change in removed)
    group = next(
        group
        for program in cleanup_catalog["programs"]
        for group in program["requirementGroups"]
        if group["groupId"] == "009216-1-000:elective-ds-pool"
    )
    numbers = {ref["courseNumber"] for ref in group["courseReferences"]}
    assert "00906292" not in numbers
    assert "00960291" in numbers


def test_cognition_track_not_mandatory_choose_n(cleanup_catalog: dict) -> None:
    apply_blocker_cleanup(cleanup_catalog, course_json_paths=[])
    group = next(
        group
        for program in cleanup_catalog["programs"]
        for group in program["requirementGroups"]
        if group["groupId"] == COGNITION_TRACK_GROUP_ID
    )
    rule = group["ruleExpression"]
    assert rule["type"] == "track_requirement"
    assert rule["operator"] == "credit_pool"
    assert rule.get("operator") != "choose_n"


def test_readiness_check_keeps_production_blocked(cleanup_catalog: dict) -> None:
    result = apply_blocker_cleanup(cleanup_catalog, course_json_paths=[])
    readiness = build_phase8_readiness_check(cleanup_catalog, result)
    assert readiness["canImportToStaging"] is True
    assert readiness["canPromoteToProduction"] is False


def test_title_enrichment_only_with_markdown_hint(cleanup_catalog: dict) -> None:
    result = apply_blocker_cleanup(cleanup_catalog, course_json_paths=[])
    enriched = [change for change in result.changes if change.action == "enrich_title"]
    assert any(change.courseNumber == "00970329" for change in enriched)
    assert not any(change.action == "correct" for change in result.changes)


def test_quality_check_passes_track_rule_after_cleanup(
    cleanup_catalog: dict,
) -> None:
    import mongomock

    apply_blocker_cleanup(cleanup_catalog, course_json_paths=[])
    client = mongomock.MongoClient()
    database = client["unipilot_test"]

    for program in cleanup_catalog["programs"]:
        database.staging_degree_programs.insert_one(
            {
                "stagingKey": f"technion-dds:catalog:2025-2026:program:{program['programCode']}",
                "program": program,
                "isStaging": True,
                "productionEligible": False,
            },
        )
        for group in program["requirementGroups"]:
            database.staging_degree_requirements.insert_one(
                {
                    "stagingKey": f"technion-dds:catalog:2025-2026:requirement:{group['groupId']}",
                    "requirementGroup": group,
                    "treatsCoursesAsMandatory": False,
                    "isStaging": True,
                    "productionEligible": False,
                },
            )

    report = build_dds_staging_quality_report(database)
    check = next(
        item for item in report.checks if item.checkId == "rules.non_executable_preserved"
    )
    assert check.passed


def test_run_blocker_cleanup_dry_run_does_not_write(tmp_path: Path, cleanup_catalog: dict) -> None:
    catalog_path = tmp_path / "catalog.json"
    readiness_path = tmp_path / "readiness.json"
    catalog_path.write_text(json.dumps(cleanup_catalog), encoding="utf-8")
    readiness_path.write_text("{}", encoding="utf-8")

    original_catalog = catalog_path.read_text(encoding="utf-8")
    summary = run_blocker_cleanup(
        catalog_path=catalog_path,
        readiness_path=readiness_path,
        cleanup_report_path=tmp_path / "cleanup.md",
        dry_run=True,
    )
    assert summary["dryRun"] is True
    assert catalog_path.read_text(encoding="utf-8") == original_catalog
    assert summary["canPromoteToProduction"] is False
