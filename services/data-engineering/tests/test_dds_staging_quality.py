"""Tests for Phase 10 DDS staging quality review."""

from pathlib import Path

import pytest

from app.config import get_settings
from app.importers.dds_catalog_staging_importer import SOURCE_NAME as DDS_CATALOG_SOURCE
from app.models.quality_report import DdsStagingQualityReport
from app.quality.dds_staging_quality import (
    accumulate_finding_severity,
    build_dds_staging_quality_report,
    find_ocr_suspect_neighbors,
    render_quality_report_markdown,
    run_dds_staging_quality_review,
    write_staging_quality_audit,
)
from app.sources.technion_course_json import SOURCE_NAME as COURSE_JSON_SOURCE
from tests.helpers.elective_chain_seed import build_advisory_requirement_group_fields

EXPECTED_PROGRAMS = ["009216-1-000", "009009-1-000", "009118-1-000"]


def _seed_minimal_staging(database, settings) -> None:
    for code in EXPECTED_PROGRAMS:
        database[settings.staging_degree_programs_collection].insert_one(
            {
                "stagingKey": f"technion-dds:catalog:2025-2026:program:{code}",
                "sourceName": DDS_CATALOG_SOURCE,
                "programCode": code,
                "totalCredits": 155.0,
                "manualReviewRequired": True,
                "productionEligible": False,
                "curationStatus": "ready-for-staging-with-review-flags",
                "signoffReview": {"reviewStatus": "ready-for-staging-with-review-flags"},
            }
        )

    statistics_chain_id = "009009-1-000:ie-statistics-elective-chain"
    chain_fields = build_advisory_requirement_group_fields(statistics_chain_id)
    database[settings.staging_degree_requirements_collection].insert_one(
        {
            "stagingKey": f"technion-dds:catalog:2025-2026:requirement:{statistics_chain_id}",
            "sourceName": DDS_CATALOG_SOURCE,
            "programCode": "009009-1-000",
            "treatsCoursesAsMandatory": False,
            "manualReviewRequired": True,
            "requirementGroup": {
                "groupId": statistics_chain_id,
                "requirementType": "elective",
                "manualReviewRequired": True,
                **chain_fields,
            },
        }
    )
    database[settings.staging_degree_requirements_collection].insert_one(
        {
            "stagingKey": "technion-dds:catalog:2025-2026:requirement:009216-1-000:semester-1-matrix",
            "sourceName": DDS_CATALOG_SOURCE,
            "programCode": "009216-1-000",
            "treatsCoursesAsMandatory": False,
            "requirementGroup": {
                "groupId": "009216-1-000:semester-1-matrix",
                "requirementType": "core",
                "courseReferences": [
                    {
                        "courseNumber": "00940345",
                        "titleHint": "מתמטיקה דיסקרטית",
                        "creditsHint": 4.0,
                    },
                    {
                        "courseNumber": "01040030",
                        "titleHint": None,
                        "creditsHint": 5.0,
                    },
                    {
                        "courseNumber": "02300401",
                        "titleHint": None,
                    },
                ],
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
            },
        }
    )

    database[settings.staging_catalog_rules_collection].insert_one(
        {
            "stagingKey": "technion-dds:catalog:2025-2026:rule:009009-1-000:ie-statistics-elective-chain",
            "sourceName": DDS_CATALOG_SOURCE,
            "programCode": "009009-1-000",
            "requirementGroupId": "009009-1-000:ie-statistics-elective-chain",
            "ruleIsExecutable": False,
            "treatsCoursesAsMandatory": False,
            "manualReviewRequired": True,
        }
    )

    database[settings.staging_courses_collection].insert_one(
        {
            "stagingKey": "technion:course:00940345",
            "sourceName": COURSE_JSON_SOURCE,
            "courseNumber": "00940345",
            "titleHebrew": "מתמטיקה דיסקרטית ת'",
            "credits": 4.0,
            "isStaging": True,
            "productionEligible": False,
            "metadata": {"degreeRequirementsInferred": False},
        }
    )
    database[settings.staging_courses_collection].insert_one(
        {
            "stagingKey": "technion:course:01040031",
            "sourceName": COURSE_JSON_SOURCE,
            "courseNumber": "01040031",
            "titleHebrew": "חדו\"א 1",
            "credits": 5.0,
            "isStaging": True,
            "productionEligible": False,
            "metadata": {"degreeRequirementsInferred": False},
        }
    )
    database[settings.staging_course_offerings_collection].insert_one(
        {
            "stagingKey": "technion:course-offering:00940345:2025:201",
            "courseNumber": "00940345",
            "isStaging": True,
            "productionEligible": False,
        }
    )


def test_quality_report_model_validation() -> None:
    report = DdsStagingQualityReport(
        reportId="test-report",
        generatedAt="2026-01-01T00:00:00+00:00",
        status="pass-with-warnings",
        recommendation="ready-for-production-promotion-design",
        summary="test summary",
    )
    assert report.sourceType == "staging_quality_review"


def test_empty_staging_yields_needs_fixes(mongo_database) -> None:
    settings = get_settings()
    report = build_dds_staging_quality_report(mongo_database, settings)
    assert report.status == "needs-fixes"
    assert report.recommendation == "needs-staging-fixes"
    assert any(f.severity == "staging-blocker" for f in report.findings)


def test_ocr_suspect_neighbor_detection() -> None:
    staged = {"01040031", "02340117", "00940345"}
    neighbors = find_ocr_suspect_neighbors("01040030", staged)
    assert "01040031" in neighbors
    neighbors2 = find_ocr_suspect_neighbors("02300401", staged)
    assert "02340117" in neighbors2


def test_quality_report_detects_missing_and_mismatches(mongo_database) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    report = build_dds_staging_quality_report(mongo_database, settings)

    assert report.counts["programs"] == 3
    assert report.missingTitleHintSummary["missingCount"] >= 2
    assert report.courseReferenceCoverage["missingInStagingCourses"]
    ocr_numbers = {
        item.get("courseNumber", "")
        for item in report.courseReferenceCoverage["ocrSuspectMissing"]
    }
    assert "02300401" in report.blockersForProduction or any(
        finding.id == "crosslink.ocr_suspect.02300401" for finding in report.findings
    )
    assert "01040030" not in ocr_numbers
    assert report.nonExecutableRuleSummary["chainRuleViolations"] == []
    assert report.counts["stagedCourses"] == 2


def test_chain_rules_stay_non_mandatory(mongo_database) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    report = build_dds_staging_quality_report(mongo_database, settings)
    assert report.nonExecutableRuleSummary["chainRuleViolations"] == []


def test_production_eligible_false_on_courses(mongo_database) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    report = build_dds_staging_quality_report(mongo_database, settings)
    check = next(c for c in report.checks if c.checkId == "courses.production_eligible_false")
    assert check.passed is True


def test_markdown_report_contains_sections(mongo_database) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    report = build_dds_staging_quality_report(mongo_database, settings)
    md = render_quality_report_markdown(report)
    assert "# DDS Staging Quality Report" in md
    assert "## Production blockers" in md
    assert "No production writes" in md


def test_write_staging_audit_only_staging_collection(mongo_database, tmp_path: Path) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    report = build_dds_staging_quality_report(mongo_database, settings)
    key = write_staging_quality_audit(mongo_database, report, settings)
    assert key.startswith("technion-dds:quality:")
    audit = mongo_database[settings.staging_data_quality_reports_collection].find_one(
        {"stagingKey": key}
    )
    assert audit is not None
    assert audit["isStaging"] is True
    assert audit["productionEligible"] is False
    assert mongo_database.courses.count_documents({}) == 0


def test_run_writes_local_reports_without_production_writes(mongo_database, tmp_path: Path) -> None:
    settings = get_settings()
    _seed_minimal_staging(mongo_database, settings)
    json_path = tmp_path / "quality.json"
    md_path = tmp_path / "quality.md"
    report = run_dds_staging_quality_review(
        mongo_database,
        settings=settings,
        json_path=json_path,
        md_path=md_path,
        write_staging_audit=False,
    )
    assert json_path.exists()
    assert md_path.exists()
    assert report.productionSafetySummary["thisCommandWritesProduction"] is False
    assert mongo_database.degree_programs.count_documents({}) == 0


@pytest.mark.parametrize(
    ("severity", "bucket"),
    [
        ("warning", "warnings"),
        ("production-blocker", "production_blockers"),
        ("api-migration-blocker", "api_blockers"),
    ],
)
def test_accumulate_finding_severity_routes_message_to_bucket(
    severity: str,
    bucket: str,
) -> None:
    warnings: list[str] = []
    production_blockers: list[str] = []
    api_blockers: list[str] = []

    accumulate_finding_severity(
        severity,
        f"{severity} message",
        warnings=warnings,
        production_blockers=production_blockers,
        api_blockers=api_blockers,
    )

    buckets = {
        "warnings": warnings,
        "production_blockers": production_blockers,
        "api_blockers": api_blockers,
    }
    assert buckets[bucket] == [f"{severity} message"]
    for name, values in buckets.items():
        if name != bucket:
            assert values == []


def test_accumulate_finding_severity_ignores_unknown_severity() -> None:
    warnings: list[str] = []
    production_blockers: list[str] = []
    api_blockers: list[str] = []

    accumulate_finding_severity(
        "info",
        "informational only",
        warnings=warnings,
        production_blockers=production_blockers,
        api_blockers=api_blockers,
    )

    assert warnings == []
    assert production_blockers == []
    assert api_blockers == []
