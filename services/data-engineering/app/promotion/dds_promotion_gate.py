"""Phase 11 — staging → production promotion gate (dry-run plan only)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.curation.catalog_policies import PRODUCTION_EXCLUDED_COURSE_NUMBERS
from app.curation.catalog_signoff import extract_catalog_signoff
from app.catalog.course_reference_policy import (
    collect_catalog_course_numbers,
    derive_production_excluded_course_numbers,
    derive_production_excluded_from_refs,
)
from app.importers.dds_catalog_staging_importer import (
    EXECUTABLE_RULE_TYPES,
    PRODUCTION_COLLECTION_NAMES,
    SOURCE_NAME as DDS_CATALOG_SOURCE,
)
from app.models.promotion import (
    PromotionCheck,
    PromotionGateResult,
    PromotionPlan,
    PromotionPlanItem,
    PromotionPolicy,
    PromotionReport,
    SkippedPromotionItem,
)
from app.quality.dds_staging_quality import (
    build_dds_staging_quality_report,
    default_json_report_path as default_quality_json_path,
)
from app.paths import default_catalog_reviewed_path, service_root
from app.sources.technion_course_json import SOURCE_NAME as COURSE_JSON_SOURCE, is_dds_faculty

EXCLUDED_COURSE_SKIP_REASON = "production-excluded-by-catalog-signoff"
EXPECTED_PROGRAM_CODES = ["009216-1-000", "009009-1-000", "009118-1-000"]
EXPECTED_TOTAL_CREDITS = 155.0

PRODUCTION_TARGET_COLLECTIONS = {
    "degreePrograms": "degree_programs",
    "catalogPathOptions": "catalog_path_options",
    "catalogFaculties": "catalog_faculties",
    "hardDegreeRequirements": "degree_requirements",
    "advisoryCatalogRules": "catalog_rules",
    "courses": "courses",
    "courseOfferings": "course_offerings",
}


def default_promotion_json_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_promotion_plan.json"


def default_promotion_md_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_promotion_plan.md"


def catalog_reviewed_json_path(faculty_id: str = "dds") -> Path:
    return default_catalog_reviewed_path(faculty_id)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _bounded_message(message: str, *, max_length: int = 500) -> str:
    if len(message) <= max_length:
        return message
    return message[: max_length - 1] + "…"


def _catalog_filter(source_name: str | None = None) -> dict[str, Any]:
    return {"sourceName": source_name or DDS_CATALOG_SOURCE}


def _catalog_source_name(faculty_id: str) -> str:
    return f"technion-{faculty_id}-catalog"


def _course_filter() -> dict[str, Any]:
    return {"sourceName": COURSE_JSON_SOURCE}


def _load_quality_summary(quality_json_path: Path | None) -> dict[str, Any]:
    path = quality_json_path or default_quality_json_path()
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "status": payload.get("status"),
            "recommendation": payload.get("recommendation"),
            "blockersForProduction": payload.get("blockersForProduction", []),
            "counts": payload.get("counts", {}),
            "sourcePath": str(path),
        }
    return {}


def _is_hard_requirement(document: dict[str, Any]) -> bool:
    group = document.get("requirementGroup", {})
    rule_type = group.get("ruleExpression", {}).get("type", "")
    return bool(document.get("ruleIsExecutable")) or rule_type in EXECUTABLE_RULE_TYPES


def _is_advisory_requirement(document: dict[str, Any], advisory_group_ids: set[str]) -> bool:
    group_id = document.get("requirementGroup", {}).get("groupId", "")
    if group_id in advisory_group_ids:
        return True
    return not _is_hard_requirement(document)


def _collect_course_refs_from_requirements(
    requirements: list[dict[str, Any]],
) -> set[str]:
    numbers: set[str] = set()
    for document in requirements:
        group = document.get("requirementGroup", {})
        for ref in group.get("courseReferences", []):
            number = ref.get("courseNumber")
            if number:
                numbers.add(number)
    return numbers


def build_promotion_gate_result(
    database: Database,
    *,
    settings: Settings | None = None,
    quality_json_path: Path | None = None,
    strict: bool = False,
    allow_warnings: bool = True,
    dry_run: bool = True,
    faculty_id: str = "dds",
) -> PromotionGateResult:
    settings = settings or get_settings()
    catalog_source = _catalog_source_name(faculty_id)
    checks: list[PromotionCheck] = []
    blockers: list[str] = []
    warnings: list[str] = []
    advisory_rule_ids: list[str] = []

    programs = list(
        database[settings.staging_degree_programs_collection].find(_catalog_filter(catalog_source))
    )
    path_options = list(
        database[settings.staging_catalog_path_options_collection].find(_catalog_filter(catalog_source))
    )
    faculties = list(
        database[settings.staging_catalog_faculties_collection].find(_catalog_filter(catalog_source))
    )
    requirements = list(
        database[settings.staging_degree_requirements_collection].find(_catalog_filter(catalog_source))
    )
    rules = list(database[settings.staging_catalog_rules_collection].find(_catalog_filter(catalog_source)))
    courses = list(database[settings.staging_courses_collection].find(_course_filter()))
    offerings = list(database[settings.staging_course_offerings_collection].find({}))

    catalog_signoff = extract_catalog_signoff(programs)
    excluded_courses = set(catalog_signoff.get("productionExcludedCourseNumbers", [])) | set(
        PRODUCTION_EXCLUDED_COURSE_NUMBERS
    )
    advisory_group_ids = set(catalog_signoff.get("signedOffNonExecutableRuleGroupIds", []))
    for document in requirements:
        group = document.get("requirementGroup", {})
        group_id = group.get("groupId")
        if group_id and not document.get("ruleIsExecutable", True):
            advisory_group_ids.add(group_id)

    quality_live = build_dds_staging_quality_report(
        database,
        settings=settings,
        faculty_id=faculty_id,
    )
    quality_file_summary = _load_quality_summary(quality_json_path)

    catalog_year: int | None = None
    catalog_version: str | None = None
    if programs:
        catalog_year = programs[0].get("catalogYear")
        catalog_version = programs[0].get("catalogVersion") or programs[0].get("sourceVersion")

    def add_check(
        check_id: str,
        passed: bool,
        message: str,
        *,
        severity: str = "info",
        details: dict[str, Any] | None = None,
        blocker: bool = False,
        warning: bool = False,
    ) -> None:
        bounded = _bounded_message(message)
        check_details = dict(details or {})
        if bounded != message:
            check_details.setdefault("fullMessage", message)
        checks.append(
            PromotionCheck(
                checkId=check_id,
                passed=passed,
                severity=severity,  # type: ignore[arg-type]
                message=bounded,
                details=check_details,
            )
        )
        if blocker and not passed:
            blockers.append(message)
        if warning and not passed:
            warnings.append(message)

    # --- Staging structure ---
    program_codes = {doc.get("programCode") for doc in programs}
    if faculty_id == "dds":
        expected_program_count = 3
        expected_codes = set(EXPECTED_PROGRAM_CODES)
        expected_credits = EXPECTED_TOTAL_CREDITS
        min_requirement_groups = 41
    else:
        expected_program_count = 1
        expected_codes = program_codes
        expected_credits = None
        min_requirement_groups = 1

    add_check(
        "staging.program_count",
        len(programs) >= expected_program_count,
        f"Found {len(programs)} staged {faculty_id} programs (expected at least {expected_program_count}).",
        severity="blocker",
        blocker=True,
    )
    missing_codes = sorted(expected_codes - program_codes) if faculty_id == "dds" else []
    add_check(
        "staging.program_codes",
        not missing_codes,
        "All expected program codes present."
        if not missing_codes
        else f"Missing program codes: {missing_codes}",
        severity="blocker",
        blocker=True,
        details={"missing": missing_codes},
    )
    if expected_credits is None:
        bad_credits = [doc.get("programCode") for doc in programs if not doc.get("totalCredits")]
    else:
        bad_credits = [
            doc.get("programCode")
            for doc in programs
            if doc.get("totalCredits") != expected_credits
        ]
    add_check(
        "staging.total_credits",
        not bad_credits,
        "All programs have valid totalCredits."
        if not bad_credits
        else f"Invalid totalCredits for: {bad_credits}",
        severity="blocker",
        blocker=True,
    )
    add_check(
        "staging.requirement_groups",
        len(requirements) >= min_requirement_groups,
        f"Found {len(requirements)} staged requirement groups.",
        severity="blocker" if len(requirements) < min_requirement_groups else "info",
        blocker=len(requirements) < min_requirement_groups,
    )
    add_check(
        "staging.courses",
        bool(courses),
        f"Found {len(courses)} staged courses.",
        severity="blocker",
        blocker=not courses,
    )
    add_check(
        "staging.offerings",
        bool(offerings),
        f"Found {len(offerings)} staged course offerings.",
        severity="blocker",
        blocker=not offerings,
    )

    # --- Staging flags ---
    bad_staging_flags = any(
        doc.get("isStaging") is not True or doc.get("productionEligible") is not False
        for doc in [*programs, *requirements, *rules, *courses, *offerings]
    )
    add_check(
        "staging.safety_flags",
        not bad_staging_flags,
        "All staging documents have isStaging=true and productionEligible=false."
        if not bad_staging_flags
        else "Some staging documents have invalid staging/production flags.",
        severity="blocker",
        blocker=bad_staging_flags,
    )

    # --- Catalog sign-off (vault wiki or legacy human) ---
    signoff_label = "vaultSignoff" if catalog_signoff.get("signoffSource") == "vault-wiki" else "catalogSignoff"
    add_check(
        "policy.catalog_signoff_present",
        bool(catalog_signoff),
        f"{signoff_label} metadata present on staged programs."
        if catalog_signoff
        else "Catalog sign-off metadata missing.",
        severity="blocker",
        blocker=not catalog_signoff,
    )
    advisory_policy_ok = catalog_signoff.get("nonExecutableRulesPolicy") == "advisory-only"
    add_check(
        "policy.non_executable_advisory",
        advisory_policy_ok,
        "nonExecutableRulesPolicy is advisory-only."
        if advisory_policy_ok
        else f"Unexpected policy: {catalog_signoff.get('nonExecutableRulesPolicy')!r}",
        severity="blocker",
        blocker=not advisory_policy_ok,
    )
    enforce_off = catalog_signoff.get("enforceNonExecutableRulesInProduction") is False
    add_check(
        "policy.no_mandatory_non_executable",
        enforce_off,
        "enforceNonExecutableRulesInProduction is false."
        if enforce_off
        else "enforceNonExecutableRulesInProduction must be false.",
        severity="blocker",
        blocker=not enforce_off,
    )
    exclude_policy_ok = (
        catalog_signoff.get("productionExcludedCoursePolicy")
        == "omit-from-production-do-not-ingest"
    )
    add_check(
        "policy.excluded_courses_policy",
        exclude_policy_ok,
        "productionExcludedCoursePolicy is omit-from-production-do-not-ingest."
        if exclude_policy_ok
        else "Unexpected productionExcludedCoursePolicy.",
        severity="blocker",
        blocker=not exclude_policy_ok,
    )
    staging_course_numbers = {
        doc.get("courseNumber") for doc in courses if doc.get("courseNumber")
    }
    catalog_refs = _collect_course_refs_from_requirements(requirements)
    dds_ingestible_course_numbers = {
        str(doc.get("courseNumber"))
        for doc in courses
        if doc.get("courseNumber") and is_dds_faculty(doc.get("faculty"))
    }
    catalog_reviewed_path = catalog_reviewed_json_path(faculty_id)
    if (
        catalog_signoff.get("signoffSource") == "vault-wiki"
        and catalog_reviewed_path.is_file()
    ):
        reviewed_document = json.loads(catalog_reviewed_path.read_text(encoding="utf-8"))
        catalog_numbers = set(collect_catalog_course_numbers(reviewed_document))
        expected_excluded = set(
            derive_production_excluded_course_numbers(
                catalog_numbers,
                ingestible_course_numbers=dds_ingestible_course_numbers,
            )
        )
    else:
        expected_excluded = derive_production_excluded_from_refs(
            catalog_refs,
            staging_course_numbers,
        )
    actual_excluded = set(catalog_signoff.get("productionExcludedCourseNumbers", []))
    excluded_match = actual_excluded == expected_excluded
    add_check(
        "policy.excluded_courses_list",
        excluded_match,
        "Production-excluded course list matches catalog refs absent from semester JSON staging."
        if excluded_match
        else f"Excluded list mismatch: extra={len(actual_excluded - expected_excluded)} "
        f"missing={len(expected_excluded - actual_excluded)} (see details).",
        severity="blocker",
        blocker=not excluded_match,
        details={
            "expected": sorted(expected_excluded),
            "actual": sorted(actual_excluded),
            "extra": sorted(actual_excluded - expected_excluded),
            "missing": sorted(expected_excluded - actual_excluded),
        },
    )
    staging_non_executable = {
        doc.get("requirementGroup", {}).get("groupId")
        for doc in requirements
        if not _is_hard_requirement(doc)
        and doc.get("requirementGroup", {}).get("groupId")
    }
    signed_off_groups = set(catalog_signoff.get("signedOffNonExecutableRuleGroupIds", []))
    non_exec_signoff_ok = staging_non_executable <= signed_off_groups
    unsigned_groups = sorted(staging_non_executable - signed_off_groups)
    if non_exec_signoff_ok:
        non_exec_message = "All staged non-executable groups are covered by catalog sign-off."
    elif len(unsigned_groups) <= 5:
        non_exec_message = f"Unsigned non-executable groups: {unsigned_groups}"
    else:
        non_exec_message = (
            f"Unsigned non-executable groups: {unsigned_groups[:5]} "
            f"(+{len(unsigned_groups) - 5} more)"
        )
    add_check(
        "policy.non_executable_groups_signed_off",
        non_exec_signoff_ok,
        non_exec_message,
        severity="blocker",
        blocker=not non_exec_signoff_ok,
    )

    # --- Quality ---
    add_check(
        "quality.no_production_blockers",
        not quality_live.blockersForProduction,
        "No production blockers in live quality review."
        if not quality_live.blockersForProduction
        else f"Production blockers remain: {quality_live.blockersForProduction[:3]}",
        severity="blocker",
        blocker=bool(quality_live.blockersForProduction),
    )
    missing_titles = quality_live.counts.get("missingTitleHints", 0)
    add_check(
        "quality.missing_title_hints",
        missing_titles == 0,
        "missingTitleHints is 0." if missing_titles == 0 else f"missingTitleHints={missing_titles}",
        severity="blocker",
        blocker=missing_titles != 0,
    )
    credit_mismatches = quality_live.counts.get("creditMismatches", 0)
    add_check(
        "quality.credit_mismatches",
        credit_mismatches == 0,
        "creditMismatches is 0."
        if credit_mismatches == 0
        else f"creditMismatches={credit_mismatches}",
        severity="blocker",
        blocker=credit_mismatches != 0,
    )
    chain_check = next(
        (check for check in quality_live.checks if check.checkId == "rules.non_executable_preserved"),
        None,
    )
    chain_ok = chain_check.passed if chain_check else True
    add_check(
        "quality.chain_rules_preserved",
        chain_ok,
        "No chain/focus rule violations."
        if chain_ok
        else "Chain/focus rule violations detected.",
        severity="blocker",
        blocker=not chain_ok,
    )
    ocr_suspects = quality_live.counts.get("ocrSuspectMissingCourses", 0)
    add_check(
        "quality.ocr_suspects",
        ocr_suspects == 0,
        "No known OCR suspect gaps."
        if ocr_suspects == 0
        else f"ocrSuspectMissingCourses={ocr_suspects}",
        severity="blocker",
        blocker=ocr_suspects != 0,
    )

    # --- Production safety (read-only) ---
    production_counts_before: dict[str, int] = {}
    for name in sorted(PRODUCTION_COLLECTION_NAMES):
        production_counts_before[name] = database[name].count_documents({})
    production_has_data = {k: v for k, v in production_counts_before.items() if v > 0}
    add_check(
        "production.collections_read_only",
        True,
        "Dry-run performed without production writes.",
    )
    if production_has_data:
        add_check(
            "production.existing_data",
            False,
            f"Production collections already contain data: {production_has_data}",
            severity="warning",
            warning=True,
            details=production_has_data,
        )

    # --- Build promotion plan ---
    plan = PromotionPlan()
    wiki_faculty_scope = f"faculty-{faculty_id}"
    policies = PromotionPolicy(
        nonExecutableRulesPolicy=str(catalog_signoff.get("nonExecutableRulesPolicy", "advisory-only")),
        enforceNonExecutableRulesInProduction=bool(
            catalog_signoff.get("enforceNonExecutableRulesInProduction", False)
        ),
        productionExcludedCoursePolicy=str(
            catalog_signoff.get("productionExcludedCoursePolicy", "omit-from-production-do-not-ingest")
        ),
        productionExcludedCourseNumbers=sorted(excluded_courses),
        signedOffBy=catalog_signoff.get("signedOffBy"),
        signedOffAt=catalog_signoff.get("signedOffAt"),
    )

    for program in programs:
        code = program.get("programCode", "")
        plan.degreePrograms.append(
            PromotionPlanItem(
                itemType="degree_program",
                stagingKey=program.get("stagingKey", code),
                productionCollection=PRODUCTION_TARGET_COLLECTIONS["degreePrograms"],
                action="upsert",
                identifier=code,
                enforceInGraduationProgress=True,
                notes="Promote program shell with catalog metadata.",
            )
        )

    for option in path_options:
        if option.get("facultyId") != wiki_faculty_scope:
            continue
        option_key = option.get("optionKey", "")
        plan.catalogPathOptions.append(
            PromotionPlanItem(
                itemType="catalog_path_option",
                stagingKey=option.get("stagingKey", option_key),
                productionCollection=PRODUCTION_TARGET_COLLECTIONS["catalogPathOptions"],
                action="upsert",
                identifier=option_key,
                enforceInGraduationProgress=False,
                notes="Profile-selectable academic path option from wiki vault.",
            )
        )

    for faculty in faculties:
        entry_faculty_id = faculty.get("facultyId", "")
        if entry_faculty_id != wiki_faculty_scope:
            continue
        plan.catalogFaculties.append(
            PromotionPlanItem(
                itemType="catalog_faculty",
                stagingKey=faculty.get("stagingKey", entry_faculty_id),
                productionCollection=PRODUCTION_TARGET_COLLECTIONS["catalogFaculties"],
                action="upsert",
                identifier=entry_faculty_id,
                enforceInGraduationProgress=False,
                notes="Technion faculty registry entry from wiki vault.",
            )
        )

    for document in requirements:
        group = document.get("requirementGroup", {})
        group_id = group.get("groupId", "")
        staging_key = document.get("stagingKey", group_id)
        if _is_hard_requirement(document):
            plan.hardDegreeRequirements.append(
                PromotionPlanItem(
                    itemType="degree_requirement",
                    stagingKey=staging_key,
                    productionCollection=PRODUCTION_TARGET_COLLECTIONS["hardDegreeRequirements"],
                    action="upsert",
                    identifier=group_id,
                    enforceInGraduationProgress=True,
                    notes="Executable credit-bucket requirement group.",
                )
            )
        elif _is_advisory_requirement(document, advisory_group_ids):
            advisory_rule_ids.append(group_id)
            plan.advisoryCatalogRules.append(
                PromotionPlanItem(
                    itemType="advisory_requirement_group",
                    stagingKey=staging_key,
                    productionCollection=PRODUCTION_TARGET_COLLECTIONS["advisoryCatalogRules"],
                    action="advisory-only",
                    identifier=group_id,
                    enforceInGraduationProgress=False,
                    notes="Non-executable group promoted as advisory metadata only.",
                )
            )
            plan.skippedItems.append(
                SkippedPromotionItem(
                    itemType="degree_requirement",
                    identifier=group_id,
                    reason="advisory-only-non-executable",
                    details={"enforceInGraduationProgress": False},
                )
            )

    promoted_course_numbers: set[str] = set()
    for course in courses:
        number = course.get("courseNumber", "")
        if not number:
            continue
        if number in excluded_courses:
            plan.skippedItems.append(
                SkippedPromotionItem(
                    itemType="course",
                    identifier=number,
                    reason="production-excluded-by-catalog-signoff",
                    details={"policy": policies.productionExcludedCoursePolicy},
                )
            )
            continue
        promoted_course_numbers.add(number)
        plan.courses.append(
            PromotionPlanItem(
                itemType="course",
                stagingKey=course.get("stagingKey", f"technion:course:{number}"),
                productionCollection=PRODUCTION_TARGET_COLLECTIONS["courses"],
                action="upsert",
                identifier=number,
                enforceInGraduationProgress=False,
                notes="Course metadata from semester JSON staging import.",
            )
        )

    for offering in offerings:
        number = offering.get("courseNumber", "")
        if number not in promoted_course_numbers:
            if number in excluded_courses:
                continue
            plan.skippedItems.append(
                SkippedPromotionItem(
                    itemType="course_offering",
                    identifier=offering.get("stagingKey", number),
                    reason="parent-course-not-promoted",
                )
            )
            continue
        plan.courseOfferings.append(
            PromotionPlanItem(
                itemType="course_offering",
                stagingKey=offering.get("stagingKey", ""),
                productionCollection=PRODUCTION_TARGET_COLLECTIONS["courseOfferings"],
                action="upsert",
                identifier=offering.get("stagingKey", number),
                enforceInGraduationProgress=False,
            )
        )

    # Excluded courses referenced only in requirements (no production course record)
    req_course_refs = _collect_course_refs_from_requirements(requirements)
    for number in sorted(req_course_refs & excluded_courses):
        if not any(
            item.identifier == number and item.reason == EXCLUDED_COURSE_SKIP_REASON
            for item in plan.skippedItems
        ):
            plan.skippedItems.append(
                SkippedPromotionItem(
                    itemType="catalog_course_reference",
                    identifier=number,
                    reason="production-excluded-by-catalog-signoff",
                    details={"note": "May remain in catalog refs as reference-only; no production course row."},
                )
            )

    excluded_in_plan = [
        item for item in plan.skippedItems if item.reason == EXCLUDED_COURSE_SKIP_REASON
    ]
    add_check(
        "plan.no_excluded_courses_in_writes",
        not any(item.itemType == "course" and item.identifier in excluded_courses for item in plan.courses),
        "Excluded courses are not in planned course writes.",
        severity="blocker",
        blocker=any(
            item.itemType == "course" and item.identifier in excluded_courses for item in plan.courses
        ),
    )
    add_check(
        "plan.advisory_rules_not_mandatory",
        all(not item.enforceInGraduationProgress for item in plan.advisoryCatalogRules),
        "All advisory catalog rules have enforceInGraduationProgress=false.",
        severity="blocker",
        blocker=any(item.enforceInGraduationProgress for item in plan.advisoryCatalogRules),
    )

    plan.counts = {
        "degreePrograms": len(plan.degreePrograms),
        "catalogPathOptions": len(plan.catalogPathOptions),
        "catalogFaculties": len(plan.catalogFaculties),
        "hardDegreeRequirements": len(plan.hardDegreeRequirements),
        "advisoryCatalogRules": len(plan.advisoryCatalogRules),
        "courses": len(plan.courses),
        "courseOfferings": len(plan.courseOfferings),
        "skippedItems": len(plan.skippedItems),
        "skippedExcludedCourses": len(excluded_in_plan),
    }

    # --- Gate status ---
    if blockers:
        gate_status = "fail"
        can_promote = False
        recommended = "Fix promotion gate blockers before Phase 12 production promotion."
    elif warnings and strict:
        gate_status = "fail"
        can_promote = False
        recommended = "Gate failed in strict mode due to warnings; resolve or use --allow-warnings."
    elif warnings and allow_warnings:
        gate_status = "pass-with-warnings"
        can_promote = True
        recommended = (
            "Gate passed with warnings. Phase 12 may implement promote-dds-to-production "
            "with explicit approval and dangerous confirmation flag."
        )
    else:
        gate_status = "pass"
        can_promote = True
        recommended = (
            "Gate passed. Phase 12 may implement promote-dds-to-production after explicit approval."
        )

    rollback_notes = [
        "Phase 11 dry-run only — no production documents were written.",
        "Phase 12 should support promotion run id + snapshot for rollback.",
        "Do not delete staging data during promotion.",
        "Advisory catalog rules must remain non-enforced in graduation progress.",
    ]

    return PromotionGateResult(
        generatedAt=_utc_now_iso(),
        sourceName=catalog_source,
        catalogYear=catalog_year,
        catalogVersion=catalog_version,
        gateStatus=gate_status,  # type: ignore[arg-type]
        canPromote=can_promote,
        dryRun=dry_run,
        checks=checks,
        policiesApplied=policies,
        plannedWrites=plan,
        advisoryRules=sorted(set(advisory_rule_ids)),
        blockers=blockers,
        warnings=warnings,
        productionSafetySummary={
            "dryRun": dry_run,
            "productionWritesPerformed": False,
            "productionCollectionCountsBefore": production_counts_before,
            "productionCollectionCountsAfter": production_counts_before,
            "productionCollectionsUnchanged": True,
        },
        rollbackNotes=rollback_notes,
        recommendedNextAction=recommended,
    )


def render_promotion_plan_markdown(report: PromotionReport) -> str:
    gate = report.gate
    plan = gate.plannedWrites
    lines = [
        "# DDS Production Promotion Plan (Phase 11 — Dry Run)",
        "",
        f"Generated: {gate.generatedAt}",
        f"Gate status: **{gate.gateStatus}**",
        f"Can promote (future Phase 12): **{gate.canPromote}**",
        "",
        "> **No production writes were performed in this phase.**",
        "",
        "## Summary",
        gate.recommendedNextAction,
        "",
        "## Policies applied",
    ]
    if gate.policiesApplied:
        p = gate.policiesApplied
        lines.extend(
            [
                f"- nonExecutableRulesPolicy: `{p.nonExecutableRulesPolicy}`",
                f"- enforceNonExecutableRulesInProduction: `{p.enforceNonExecutableRulesInProduction}`",
                f"- productionExcludedCoursePolicy: `{p.productionExcludedCoursePolicy}`",
                f"- productionExcludedCourseNumbers: {len(p.productionExcludedCourseNumbers)} courses",
                f"- signedOffBy: {p.signedOffBy} at {p.signedOffAt}",
            ]
        )
    lines.append("")
    lines.append("## Planned production writes (counts)")
    for key, value in plan.counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Target collections")
    for logical, collection in PRODUCTION_TARGET_COLLECTIONS.items():
        lines.append(f"- {logical} → `{collection}`")
    lines.append("")
    lines.append("## Advisory rule handling")
    lines.append(
        f"- {len(gate.advisoryRules)} rule/group identifiers promoted as **advisory-only** "
        "(enforceInGraduationProgress=false)."
    )
    lines.append("")
    lines.append("## Skipped / excluded courses")
    excluded = [
        item
        for item in plan.skippedItems
        if item.reason == EXCLUDED_COURSE_SKIP_REASON
    ]
    if excluded:
        for item in excluded[:20]:
            lines.append(f"- `{item.identifier}` — {item.reason}")
        if len(excluded) > 20:
            lines.append(f"- ... and {len(excluded) - 20} more")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Gate checks")
    for check in gate.checks:
        mark = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{mark}] {check.checkId}: {check.message}")
    lines.append("")
    if gate.warnings:
        lines.append("## Warnings")
        for warning in gate.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    if gate.blockers:
        lines.append("## Blockers")
        for blocker in gate.blockers:
            lines.append(f"- {blocker}")
        lines.append("")
    lines.append("## Production safety")
    lines.append("- **No production collection writes occurred.**")
    counts = gate.productionSafetySummary.get("productionCollectionCountsBefore", {})
    nonempty = {k: v for k, v in counts.items() if v}
    if nonempty:
        lines.append(f"- Existing production data (review only): {nonempty}")
    else:
        lines.append("- Production collections are empty.")
    lines.append("")
    lines.append("## Rollback notes")
    for note in gate.rollbackNotes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("## Phase 12 recommendation")
    lines.append(
        "Implement `promote-dds-to-production` only after explicit approval, "
        "with `--i-confirm-dangerous-production-write` and idempotent upsert semantics."
    )
    return "\n".join(lines) + "\n"


def write_promotion_report_files(
    report: PromotionReport,
    *,
    json_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_promotion_plan_markdown(report), encoding="utf-8")


def run_promotion_gate_plan(
    database: Database,
    *,
    settings: Settings | None = None,
    json_path: Path | None = None,
    md_path: Path | None = None,
    quality_json_path: Path | None = None,
    strict: bool = False,
    allow_warnings: bool = True,
    faculty_id: str = "dds",
) -> PromotionReport:
    settings = settings or get_settings()
    gate = build_promotion_gate_result(
        database,
        settings=settings,
        quality_json_path=quality_json_path,
        strict=strict,
        allow_warnings=allow_warnings,
        dry_run=True,
        faculty_id=faculty_id,
    )
    quality_summary = _load_quality_summary(quality_json_path)
    if not quality_summary:
        live = build_dds_staging_quality_report(database, settings=settings, faculty_id=faculty_id)
        quality_summary = {
            "status": live.status,
            "recommendation": live.recommendation,
            "blockersForProduction": live.blockersForProduction,
            "counts": live.counts,
            "sourcePath": "live-computed",
        }

    report = PromotionReport(gate=gate, qualityReportSummary=quality_summary)
    out_json = json_path or default_promotion_json_path()
    out_md = md_path or default_promotion_md_path()
    write_promotion_report_files(report, json_path=out_json, md_path=out_md)
    return report


def assert_production_unchanged(
    database: Database,
    counts_before: dict[str, int],
) -> bool:
    for name, before in counts_before.items():
        if database[name].count_documents({}) != before:
            return False
    return True
