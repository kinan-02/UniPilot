"""Tests for vault wiki vs production parity verification."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.promotion.dds_production_promoter import (
    map_staging_advisory_requirement_to_production,
    map_staging_requirement_to_production,
)
from app.promotion.dds_promotion_gate import _is_advisory_requirement, _is_hard_requirement
from app.vault.export_dds_catalog import export_vault_catalog
from app.vault.vault_signoff import apply_vault_signoff_to_catalog
from app.vault.verify_vault_production_parity import (
    build_expected_groups_from_vault_document,
    compare_group_snapshots,
    load_production_groups,
    verify_vault_production_parity,
)


@pytest.fixture
def vault_document():
    document, _ = export_vault_catalog(faculty="dds")
    apply_vault_signoff_to_catalog(document)
    return document


def test_vault_export_has_expected_program_and_group_counts(vault_document) -> None:
    expected = build_expected_groups_from_vault_document(vault_document)
    hard = [gid for gid, snap in expected.items() if snap.classification == "hard"]
    advisory = [gid for gid, snap in expected.items() if snap.classification == "advisory"]
    assert len(vault_document["programs"]) == 3
    assert len(expected) == len(hard) + len(advisory)
    assert len(hard) >= 1
    assert len(advisory) >= 1


def test_promoted_production_matches_vault_export(mongo_database, vault_document) -> None:
    settings = get_settings()
    signoff = vault_document["curationReport"]["vaultSignoff"]
    advisory_group_ids = set(signoff["signedOffNonExecutableRuleGroupIds"])

    for program in vault_document["programs"]:
        for group in program["requirementGroups"]:
            group_id = group["groupId"]
            staging = {
                "programCode": program["programCode"],
                "institutionId": program["institutionId"],
                "catalogYear": program["catalogYear"],
                "requirementGroup": group,
                "ruleIsExecutable": group["ruleExpression"]["type"] == "credit_bucket",
                "stagingKey": f"test:{group_id}",
            }
            if _is_hard_requirement(staging):
                doc = map_staging_requirement_to_production(
                    staging,
                    promotion_run_id="test-run",
                    promoted_at="2026-01-01T00:00:00+00:00",
                    catalog_version="2025-2026",
                )
                mongo_database[settings.production_degree_requirements_collection].insert_one(doc)
            elif _is_advisory_requirement(staging, advisory_group_ids):
                doc = map_staging_advisory_requirement_to_production(
                    staging,
                    promotion_run_id="test-run",
                    promoted_at="2026-01-01T00:00:00+00:00",
                    catalog_version="2025-2026",
                )
                mongo_database[settings.production_catalog_rules_collection].insert_one(doc)

    result = verify_vault_production_parity(mongo_database, faculty="dds")
    assert result.ok, (
        f"missing={result.missing_in_production}, extra={result.extra_in_production}, "
        f"classification={result.classification_mismatches}, fields={result.field_mismatches[:5]}"
    )
    assert result.matched_groups == len(build_expected_groups_from_vault_document(vault_document))


def test_compare_group_snapshots_detects_course_number_drift(vault_document) -> None:
    expected = build_expected_groups_from_vault_document(vault_document)
    sample = next(iter(expected.values()))
    drifted = sample
    actual = type(sample)(
        group_id=drifted.group_id,
        program_code=drifted.program_code,
        classification=drifted.classification,
        title=drifted.title,
        requirement_type=drifted.requirement_type,
        min_credits=drifted.min_credits,
        rule_type=drifted.rule_type,
        rule_operator=drifted.rule_operator,
        rule_min_credits=drifted.rule_min_credits,
        rule_semester=drifted.rule_semester,
        course_numbers=("00999999",),
        course_refs=(("00999999", None),),
    )
    mismatches = compare_group_snapshots(sample, actual, expected_all={sample.group_id: sample})
    assert any(item.field == "courseNumbers" for item in mismatches)


def test_load_production_groups_skips_legacy_catalog_rule_rows(mongo_database) -> None:
    settings = get_settings()
    mongo_database[settings.production_catalog_rules_collection].insert_many(
        [
            {
                "requirementGroupId": "009216-1-000:semester-1-matrix",
                "recordType": "catalog_rule",
                "programCode": "009216-1-000",
                "courseReferences": [],
            },
            {
                "requirementGroupId": "009216-1-000:semester-1-matrix",
                "recordType": "advisory_requirement_group",
                "programCode": "009216-1-000",
                "courseReferences": [{"courseNumber": "00940345"}],
                "ruleExpression": {"type": "semester_matrix", "semester": 1},
            },
        ]
    )
    loaded = load_production_groups(mongo_database)
    assert list(loaded.keys()) == ["009216-1-000:semester-1-matrix"]
    assert loaded["009216-1-000:semester-1-matrix"].course_numbers == ("00940345",)
