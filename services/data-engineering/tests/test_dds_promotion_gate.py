"""Tests for Phase 11 DDS production promotion gate (dry-run)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.config import get_settings
from app.curation.catalog_policies import (
    PRODUCTION_EXCLUDED_COURSE_NUMBERS,
    build_catalog_signoff_payload,
)
from app.importers.dds_catalog_staging_importer import PRODUCTION_COLLECTION_NAMES, SOURCE_NAME as DDS_CATALOG_SOURCE
from app.main import run_plan_dds_production_promotion, run_promote_dds_to_production
from app.promotion.dds_promotion_gate import (
    EXCLUDED_COURSE_SKIP_REASON,
    _collect_course_refs_from_requirements,
    build_promotion_gate_result,
    catalog_reviewed_json_path,
    render_promotion_plan_markdown,
    run_promotion_gate_plan,
)
from app.models.promotion import PromotionReport
from app.sources.technion_course_json import SOURCE_NAME as COURSE_JSON_SOURCE
from tests.helpers.elective_chain_seed import build_advisory_requirement_group_fields

EXPECTED_PROGRAMS = ["009216-1-000", "009009-1-000", "009118-1-000"]
SEED_ADVISORY_GROUP_IDS = (
    "009216-1-000:semester-1-matrix",
    "009216-1-000:semester-2-matrix",
    "009216-1-000:semester-3-matrix",
    "009216-1-000:semester-4-matrix",
    "009216-1-000:semester-5-matrix",
    "009216-1-000:semester-7-matrix",
    "009216-1-000:semester-8-matrix",
    "009216-1-000:elective-ds-pool",
    "009216-1-000:elective-faculty-pool",
    "009216-1-000:cognition-track:requirements",
    "009216-1-000:math-analytics-track:requirements",
    "009009-1-000:semester-1-matrix",
    "009009-1-000:semester-2-matrix",
    "009009-1-000:semester-3-matrix",
    "009009-1-000:semester-4-matrix",
    "009009-1-000:semester-5-matrix",
    "009009-1-000:semester-6-matrix",
    "009009-1-000:semester-7-matrix",
    "009009-1-000:semester-8-matrix",
    "009009-1-000:ie-statistics-elective-chain",
    "009009-1-000:ie-behavior-science-chain",
    "009009-1-000:ie-focus-chain-game-theory",
    "009009-1-000:ie-focus-chain-advanced-industry",
    "009009-1-000:ie-focus-chain-operations-research",
    "009009-1-000:ie-additional-faculty-electives",
    "009118-1-000:semester-1-matrix",
    "009118-1-000:semester-2-matrix",
    "009118-1-000:semester-3-matrix",
    "009118-1-000:semester-4-matrix",
    "009118-1-000:semester-5-matrix",
    "009118-1-000:semester-7-matrix",
    "009118-1-000:semester-8-matrix",
    "009118-1-000:is-behavior-science-chain",
    "009118-1-000:is-focus-chain-performance",
    "009118-1-000:is-focus-chain-ml",
    "009118-1-000:is-focus-chain-game-theory",
    "009118-1-000:is-additional-faculty-electives",
)
HARD_GROUP_IDS = [
    "009216-1-000:core-mandatory",
    "009216-1-000:math-electives",
    "009216-1-000:faculty-electives",
    "009009-1-000:core-mandatory",
    "009009-1-000:ie-electives",
    "009009-1-000:statistics-bucket",
    "009118-1-000:core-mandatory",
    "009118-1-000:is-electives",
    "009118-1-000:systems-bucket",
    "009216-1-000:ds-project-bucket",
    "009216-1-000:seminar-bucket",
    "009009-1-000:project-bucket",
    "009009-1-000:seminar-bucket",
    "009118-1-000:project-bucket",
    "009118-1-000:seminar-bucket",
    "009216-1-000:english-bucket",
    "009009-1-000:english-bucket",
    "009118-1-000:english-bucket",
    "009216-1-000:ethics-bucket",
]


def _staging_doc_flags() -> dict[str, bool]:
    return {"isStaging": True, "productionEligible": False}


def _build_seed_catalog_signoff(*, excluded_numbers: list[str]) -> dict[str, object]:
    return build_catalog_signoff_payload(
        signed_off_by="test-reviewer",
        excluded_course_numbers=excluded_numbers,
        non_executable_group_ids=list(SEED_ADVISORY_GROUP_IDS),
    )


def _seed_signed_off_promotion_staging(database, *, include_catalog_signoff: bool = True) -> None:
    settings = get_settings()
    flags = _staging_doc_flags()
    requirement_docs: list[dict[str, object]] = []

    for group_id in HARD_GROUP_IDS:
        program_code = group_id.split(":")[0]
        requirement_docs.append(
            {
                "stagingKey": f"technion-dds:catalog:2025-2026:requirement:{group_id}",
                "sourceName": DDS_CATALOG_SOURCE,
                "programCode": program_code,
                "ruleIsExecutable": True,
                "treatsCoursesAsMandatory": False,
                "requirementGroup": {
                    "groupId": group_id,
                    "requirementType": "core",
                    "courseReferences": [],
                    "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
                },
                **flags,
            }
        )

    for group_id in SEED_ADVISORY_GROUP_IDS:
        program_code = group_id.split(":")[0]
        chain_fields = build_advisory_requirement_group_fields(group_id)
        if group_id.endswith("elective-ds-pool"):
            chain_fields = {
                **chain_fields,
                "courseReferences": [
                    {
                        "courseNumber": PRODUCTION_EXCLUDED_COURSE_NUMBERS[0],
                        "titleHint": "Excluded ref",
                    }
                ],
            }
        requirement_docs.append(
            {
                "stagingKey": f"technion-dds:catalog:2025-2026:requirement:{group_id}",
                "sourceName": DDS_CATALOG_SOURCE,
                "programCode": program_code,
                "ruleIsExecutable": False,
                "treatsCoursesAsMandatory": False,
                "requirementGroup": {
                    "groupId": group_id,
                    "requirementType": "elective",
                    **chain_fields,
                },
                **flags,
            }
        )

    catalog_refs = _collect_course_refs_from_requirements(requirement_docs)
    promoted_numbers = ["00940345", "01040031", "02340117"]
    staging_numbers = set(promoted_numbers)
    for number in catalog_refs:
        if number not in PRODUCTION_EXCLUDED_COURSE_NUMBERS:
            staging_numbers.add(number)
    expected_excluded = sorted(catalog_refs - staging_numbers)
    catalog_signoff = _build_seed_catalog_signoff(excluded_numbers=expected_excluded)

    for code in EXPECTED_PROGRAMS:
        program_doc = {
            "stagingKey": f"technion-dds:catalog:2025-2026:program:{code}",
            "sourceName": DDS_CATALOG_SOURCE,
            "programCode": code,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "totalCredits": 155.0,
            "manualReviewRequired": True,
            "curationStatus": "ready-for-staging-with-review-flags",
            "signoffReview": {"reviewStatus": "ready-for-staging-with-review-flags"},
            **flags,
        }
        if include_catalog_signoff:
            program_doc["curationReport"] = {"vaultSignoff": catalog_signoff}
        database[settings.staging_degree_programs_collection].insert_one(program_doc)

    for document in requirement_docs:
        database[settings.staging_degree_requirements_collection].insert_one(document)

    for number in sorted(staging_numbers):
        database[settings.staging_courses_collection].insert_one(
            {
                "stagingKey": f"technion:course:{number}",
                "sourceName": COURSE_JSON_SOURCE,
                "courseNumber": number,
                "titleHebrew": f"Course {number}",
                "credits": 4.0,
                "metadata": {"degreeRequirementsInferred": False},
                **flags,
            }
        )
        database[settings.staging_course_offerings_collection].insert_one(
            {
                "stagingKey": f"technion:course-offering:{number}:2025:201",
                "sourceName": COURSE_JSON_SOURCE,
                "courseNumber": number,
                **flags,
            }
        )


def test_gate_passes_with_signed_off_staging(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    assert gate.gateStatus in {"pass", "pass-with-warnings"}
    assert gate.canPromote is True
    assert gate.dryRun is True
    assert gate.plannedWrites.counts["degreePrograms"] == 3
    assert gate.plannedWrites.counts["hardDegreeRequirements"] == len(HARD_GROUP_IDS)


def test_gate_fails_without_catalog_signoff(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database, include_catalog_signoff=False)
    gate = build_promotion_gate_result(mongo_database)
    assert gate.gateStatus == "fail"
    assert gate.canPromote is False
    assert any(check.checkId == "policy.catalog_signoff_present" and not check.passed for check in gate.checks)


def _set_vault_signoff_on_all_programs(
    database,
    *,
    mutator: Callable[[dict], None],
) -> None:
    settings = get_settings()
    for program in database[settings.staging_degree_programs_collection].find({}):
        signoff = dict(program["curationReport"]["vaultSignoff"])
        mutator(signoff)
        database[settings.staging_degree_programs_collection].update_one(
            {"_id": program["_id"]},
            {"$set": {"curationReport.vaultSignoff": signoff}},
        )


def test_gate_fails_if_excluded_course_list_missing(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)

    def clear_excluded(signoff: dict) -> None:
        signoff["productionExcludedCourseNumbers"] = []

    _set_vault_signoff_on_all_programs(mongo_database, mutator=clear_excluded)
    gate = build_promotion_gate_result(mongo_database)
    assert gate.gateStatus == "fail"
    assert any(check.checkId == "policy.excluded_courses_list" and not check.passed for check in gate.checks)


def test_excluded_courses_not_in_planned_course_writes(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    planned_numbers = {item.identifier for item in gate.plannedWrites.courses}
    assert not planned_numbers.intersection(PRODUCTION_EXCLUDED_COURSE_NUMBERS)
    skipped = {
        item.identifier
        for item in gate.plannedWrites.skippedItems
        if item.reason == EXCLUDED_COURSE_SKIP_REASON
    }
    assert PRODUCTION_EXCLUDED_COURSE_NUMBERS[0] in skipped


def test_non_executable_rules_become_advisory(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    assert gate.plannedWrites.counts["advisoryCatalogRules"] >= len(SEED_ADVISORY_GROUP_IDS)
    assert all(not item.enforceInGraduationProgress for item in gate.plannedWrites.advisoryCatalogRules)
    hard_ids = {item.identifier for item in gate.plannedWrites.hardDegreeRequirements}
    assert not hard_ids.intersection(set(SEED_ADVISORY_GROUP_IDS))


def test_advisory_plan_uses_requirement_groups_only(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    advisory_types = {item.itemType for item in gate.plannedWrites.advisoryCatalogRules}
    assert advisory_types == {"advisory_requirement_group"}
    assert not any(item.itemType == "catalog_rule" for item in gate.plannedWrites.skippedItems)


def test_gate_fails_on_credit_mismatches(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.staging_degree_requirements_collection].update_one(
        {"requirementGroup.groupId": HARD_GROUP_IDS[0]},
        {
            "$set": {
                "requirementGroup.courseReferences": [
                    {
                        "courseNumber": "00940345",
                        "titleHint": "Discrete Math",
                        "creditsHint": 9.0,
                    }
                ]
            }
        },
    )
    gate = build_promotion_gate_result(mongo_database)
    assert gate.gateStatus == "fail"
    assert any(check.checkId == "quality.credit_mismatches" and not check.passed for check in gate.checks)


def test_gate_fails_on_missing_title_hints(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.staging_degree_requirements_collection].update_one(
        {"requirementGroup.groupId": HARD_GROUP_IDS[0]},
        {
            "$set": {
                "requirementGroup.courseReferences": [
                    {"courseNumber": "00940345", "titleHint": None},
                ]
            }
        },
    )
    gate = build_promotion_gate_result(mongo_database)
    assert gate.gateStatus == "fail"
    assert any(check.checkId == "quality.missing_title_hints" and not check.passed for check in gate.checks)


def test_gate_fails_on_chain_rule_violations(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.staging_degree_requirements_collection].update_one(
        {"requirementGroup.groupId": "009009-1-000:ie-statistics-elective-chain"},
        {"$set": {"treatsCoursesAsMandatory": True}},
    )
    gate = build_promotion_gate_result(mongo_database)
    assert gate.gateStatus == "fail"
    assert any(check.checkId == "quality.chain_rules_preserved" and not check.passed for check in gate.checks)


def test_dry_run_writes_no_production_collections(mongo_database, tmp_path: Path) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    before = {name: mongo_database[name].count_documents({}) for name in PRODUCTION_COLLECTION_NAMES}
    report = run_promotion_gate_plan(
        mongo_database,
        json_path=tmp_path / "plan.json",
        md_path=tmp_path / "plan.md",
        allow_warnings=True,
    )
    after = {name: mongo_database[name].count_documents({}) for name in PRODUCTION_COLLECTION_NAMES}
    assert before == after
    assert report.gate.productionSafetySummary["productionWritesPerformed"] is False


def test_promotion_command_refuses_without_dangerous_flag(mongo_database, monkeypatch) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    monkeypatch.setattr("app.main.check_mongo_connectivity", lambda: "connected")
    before = {name: mongo_database[name].count_documents({}) for name in PRODUCTION_COLLECTION_NAMES}
    exit_code = run_promote_dds_to_production(
        confirm_dangerous=False,
        dry_run=False,
        allow_warnings=True,
        output_json=None,
        output_md=None,
    )
    after = {name: mongo_database[name].count_documents({}) for name in PRODUCTION_COLLECTION_NAMES}
    assert exit_code == 2
    assert before == after


def test_markdown_report_contains_required_sections(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    markdown = render_promotion_plan_markdown(PromotionReport(gate=gate))
    assert "Policies applied" in markdown
    assert "Planned production writes" in markdown
    assert "Skipped / excluded courses" in markdown
    assert "No production collection writes occurred" in markdown
    assert "advisory-only" in markdown


def test_strict_mode_fails_on_warnings(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database.degree_programs.insert_one({"programCode": "legacy", "name": "old"})
    gate = build_promotion_gate_result(mongo_database, strict=True, allow_warnings=False)
    if gate.warnings:
        assert gate.gateStatus == "fail"
        assert gate.canPromote is False


def test_promotion_gate_non_dds_structure_checks(mongo_database) -> None:
    from app.config import get_settings
    from app.promotion.dds_promotion_gate import build_promotion_gate_result

    settings = get_settings()
    source = "technion-math-catalog"
    mongo_database[settings.staging_degree_programs_collection].insert_one(
        {
            "sourceName": source,
            "programCode": "010001-1-000",
            "totalCredits": None,
            "catalogVersion": "2025-2026",
            "isStaging": True,
            "productionEligible": False,
        }
    )
    mongo_database[settings.staging_degree_requirements_collection].delete_many({})
    mongo_database[settings.staging_courses_collection].insert_one(
        {"sourceName": "technion-course-json", "courseNumber": "01000101"}
    )
    mongo_database[settings.staging_course_offerings_collection].insert_one(
        {"courseNumber": "01000101", "stagingKey": "technion:offering:01000101"}
    )
    gate = build_promotion_gate_result(
        mongo_database,
        settings=settings,
        faculty_id="math",
        allow_warnings=True,
    )
    assert gate.sourceName == source
    assert any(check.checkId == "staging.total_credits" and not check.passed for check in gate.checks)


def test_catalog_reviewed_json_path_points_to_generated_catalog() -> None:
    path = catalog_reviewed_json_path()
    assert path.as_posix().endswith("generated/technion/catalog/catalog_reviewed.json")
    cs_path = catalog_reviewed_json_path("computer-science")
    assert cs_path.as_posix().endswith("generated/technion/computer-science/catalog_reviewed.json")


def test_gate_recomputes_excluded_courses_from_vault_export(
    mongo_database,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reviewed_path = tmp_path / "catalog_reviewed.json"
    reviewed_path.write_text(
        json.dumps(
            {
                "programs": [
                    {
                        "requirementGroups": [
                            {
                                "courseReferences": [
                                    {"courseNumber": "00940345"},
                                    {"courseNumber": "00960226"},
                                ]
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.promotion.dds_promotion_gate.catalog_reviewed_json_path",
        lambda faculty_id="dds": reviewed_path,
    )
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.staging_courses_collection].update_one(
        {"courseNumber": "00940345"},
        {"$set": {"faculty": "הפקולטה למדעי הנתונים וההחלטות"}},
    )

    def set_excluded(signoff: dict) -> None:
        signoff["signoffSource"] = "vault-wiki"
        signoff["productionExcludedCourseNumbers"] = ["00960226"]

    _set_vault_signoff_on_all_programs(mongo_database, mutator=set_excluded)

    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    excluded_check = next(
        check for check in gate.checks if check.checkId == "policy.excluded_courses_list"
    )
    assert excluded_check.passed is True


def test_gate_excluded_list_honors_technion_semester_json_scope(
    mongo_database, tmp_path: Path, monkeypatch
) -> None:
    reviewed_path = tmp_path / "catalog_reviewed.json"
    reviewed_path.write_text(
        json.dumps(
            {
                "programs": [
                    {
                        "requirementGroups": [
                            {
                                "courseReferences": [
                                    {"courseNumber": "00940345"},
                                    {"courseNumber": "00999999"},
                                ]
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.promotion.dds_promotion_gate.catalog_reviewed_json_path",
        lambda faculty_id="dds": reviewed_path,
    )
    _seed_signed_off_promotion_staging(mongo_database)

    def set_technion_scope(signoff: dict) -> None:
        signoff["signoffSource"] = "vault-wiki"
        signoff["ingestibleCourseScope"] = "technion-semester-json"
        signoff["productionExcludedCourseNumbers"] = ["00999999"]

    _set_vault_signoff_on_all_programs(mongo_database, mutator=set_technion_scope)

    gate = build_promotion_gate_result(mongo_database, allow_warnings=True)
    excluded_check = next(
        check for check in gate.checks if check.checkId == "policy.excluded_courses_list"
    )
    assert excluded_check.passed is True


def test_cli_plan_command_exits_zero_on_pass(mongo_database, tmp_path: Path, monkeypatch) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    monkeypatch.setattr("app.main.check_mongo_connectivity", lambda: "connected")
    exit_code = run_plan_dds_production_promotion(
        str(tmp_path / "plan.json"),
        str(tmp_path / "plan.md"),
        strict=False,
        allow_warnings=True,
    )
    assert exit_code == 0
    assert (tmp_path / "plan.json").exists()
    assert (tmp_path / "plan.md").exists()
