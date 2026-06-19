"""Tests for human DDS catalog sign-off policy."""

from __future__ import annotations

import json
from pathlib import Path

import mongomock

from app.curation.dds_catalog_human_signoff import (
    NON_EXECUTABLE_RULE_GROUP_IDS,
    PRODUCTION_EXCLUDED_COURSE_NUMBERS,
    apply_human_signoff_to_catalog,
    run_record_human_signoff,
)
from app.quality.dds_staging_quality import build_dds_staging_quality_report

FIXTURE = Path(__file__).parent / "fixtures" / "dds_catalog_blocker_cleanup_fixture.json"


def test_human_signoff_marks_rules_advisory_only() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    human = apply_human_signoff_to_catalog(document)
    assert human["enforceNonExecutableRulesInProduction"] is False
    assert len(human["signedOffNonExecutableRuleGroupIds"]) == len(NON_EXECUTABLE_RULE_GROUP_IDS)
    assert len(human["productionExcludedCourseNumbers"]) == len(PRODUCTION_EXCLUDED_COURSE_NUMBERS)


def test_quality_report_ignores_signed_off_gaps(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    apply_human_signoff_to_catalog(document)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(document), encoding="utf-8")
    run_record_human_signoff(catalog_path=catalog_path, readiness_path=tmp_path / "ready.json")

    client = mongomock.MongoClient()
    database = client["test"]
    human = document["curationReport"]["humanSignoff"]
    database.staging_degree_programs.insert_one(
        {
            "programCode": "009216-1-000",
            "curationReport": {"humanSignoff": human},
            "sourceName": "technion-dds-catalog",
        },
    )
    database.staging_degree_requirements.insert_one(
        {
            "requirementGroup": {
                "groupId": "009216-1-000:elective-ds-pool",
                "ruleExpression": {"type": "course_pool"},
                "courseReferences": [
                    {"courseNumber": excluded, "titleHint": "x"}
                    for excluded in PRODUCTION_EXCLUDED_COURSE_NUMBERS[:2]
                ],
            },
            "treatsCoursesAsMandatory": False,
            "sourceName": "technion-dds-catalog",
        },
    )

    report = build_dds_staging_quality_report(database)
    assert not any("non-executable" in blocker.lower() for blocker in report.blockersForProduction)
    assert report.counts["productionExcludedCatalogCourseReferences"] >= 2
