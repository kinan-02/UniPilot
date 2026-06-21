"""Phase 10 — staging data quality review and cross-link validation."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.importers.dds_catalog_staging_importer import (
    EXECUTABLE_RULE_TYPES,
    PRODUCTION_COLLECTION_NAMES,
    assert_staging_collection_name,
)
from app.curation.catalog_signoff import extract_catalog_signoff
from app.models.quality_report import (
    DdsStagingQualityReport,
    QualityCheckResult,
    QualityFinding,
)
from app.sources.technion_course_json import SOURCE_NAME as COURSE_JSON_SOURCE
from app.paths import service_root

DDS_CATALOG_SOURCE = "technion-dds-catalog"
QUALITY_SOURCE_NAME = "technion-dds-staging-quality"
QUALITY_SOURCE_TYPE = "staging_quality_review"

EXPECTED_PROGRAM_CODES = ["009216-1-000", "009009-1-000", "009118-1-000"]
EXPECTED_TOTAL_CREDITS = 155.0
EXPECTED_REQUIREMENT_GROUPS = 41
EXPECTED_CATALOG_RULES = 22
EXPECTED_CURATION_STATUS = "ready-for-staging-with-review-flags"

KNOWN_OCR_SUSPECT_NUMBERS = frozenset({"00906292", "01040030", "02300401"})
KNOWN_OCR_NEIGHBORS: dict[str, list[str]] = {
    "00906292": ["00960292", "00960291"],
    "01040030": ["01040031"],
    "02300401": ["02340117", "02340116"],
}

COURSE_NUMBER_PATTERN = re.compile(r"^0\d{7}$")


def default_json_report_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_staging_quality_report.json"


def default_md_report_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_staging_quality_report.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_ocr_suspect_neighbors(missing_number: str, staged_numbers: set[str]) -> list[str]:
    neighbors: list[str] = []
    for candidate in KNOWN_OCR_NEIGHBORS.get(missing_number, []):
        if candidate in staged_numbers:
            neighbors.append(candidate)

    scored: list[tuple[float, str]] = []
    for staged in staged_numbers:
        if staged == missing_number:
            continue
        ratio = _similarity(missing_number, staged)
        if ratio >= 0.75 or (
            missing_number[:5] == staged[:5] and abs(len(missing_number) - len(staged)) <= 1
        ):
            scored.append((ratio, staged))
    scored.sort(reverse=True)
    for _ratio, staged in scored[:3]:
        if staged not in neighbors:
            neighbors.append(staged)
    return neighbors


def _catalog_filter() -> dict[str, str]:
    return {"sourceName": DDS_CATALOG_SOURCE}


def _course_filter() -> dict[str, str]:
    return {"sourceName": COURSE_JSON_SOURCE}


def _collect_course_references(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for document in requirements:
        group = document.get("requirementGroup", {})
        group_id = group.get("groupId", document.get("stagingKey", "unknown"))
        program_code = document.get("programCode", "unknown")
        for ref in group.get("courseReferences", []):
            refs.append(
                {
                    **ref,
                    "groupId": group_id,
                    "programCode": program_code,
                }
            )
    return refs


def _count_manual_review_items(
    programs: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    by_program: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0

    for program in programs:
        if program.get("manualReviewRequired", True):
            total += 1
            code = program.get("programCode", "unknown")
            by_program[code] = by_program.get(code, 0) + 1

    for document in requirements:
        group = document.get("requirementGroup", {})
        if document.get("manualReviewRequired", True) or group.get("manualReviewRequired", True):
            total += 1
            code = document.get("programCode", "unknown")
            by_program[code] = by_program.get(code, 0) + 1
            req_type = group.get("requirementType", "unknown")
            by_type[req_type] = by_type.get(req_type, 0) + 1
        for ref in group.get("courseReferences", []):
            if ref.get("manualReviewRequired", True):
                total += 1

    for rule in rules:
        if rule.get("manualReviewRequired", True):
            total += 1
            code = rule.get("programCode", "unknown")
            by_program[code] = by_program.get(code, 0) + 1
            by_type["catalog_rule"] = by_type.get("catalog_rule", 0) + 1

    return {
        "total": total,
        "byProgram": dict(sorted(by_program.items())),
        "byRequirementType": dict(sorted(by_type.items())),
    }


def build_dds_staging_quality_report(
    database: Database,
    settings: Settings | None = None,
) -> DdsStagingQualityReport:
    settings = settings or get_settings()
    findings: list[QualityFinding] = []
    checks: list[QualityCheckResult] = []
    warnings: list[str] = []
    production_blockers: list[str] = []
    api_blockers: list[str] = []
    recommendations: list[str] = []

    programs = list(database[settings.staging_degree_programs_collection].find(_catalog_filter()))
    requirements = list(
        database[settings.staging_degree_requirements_collection].find(_catalog_filter())
    )
    rules = list(database[settings.staging_catalog_rules_collection].find(_catalog_filter()))
    courses = list(database[settings.staging_courses_collection].find(_course_filter()))
    offerings = list(database[settings.staging_course_offerings_collection].find({}))
    staged_course_numbers = {doc.get("courseNumber") for doc in courses if doc.get("courseNumber")}
    catalog_signoff = extract_catalog_signoff(programs)
    production_excluded_courses = set(catalog_signoff.get("productionExcludedCourseNumbers", []))
    non_executable_signed_off = (
        catalog_signoff.get("enforceNonExecutableRulesInProduction") is False
        and bool(catalog_signoff.get("signedOffNonExecutableRuleGroupIds"))
    )

    def add_finding(
        finding_id: str,
        severity: str,
        category: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        findings.append(
            QualityFinding(
                id=finding_id,
                severity=severity,  # type: ignore[arg-type]
                category=category,
                message=message,
                details=details or {},
            )
        )
        if severity == "warning":
            warnings.append(message)
        elif severity == "production-blocker":
            production_blockers.append(message)
        elif severity == "api-migration-blocker":
            api_blockers.append(message)

    # --- Catalog structure ---
    program_codes = [doc.get("programCode") for doc in programs]
    programs_ok = len(programs) == 3 and program_codes == EXPECTED_PROGRAM_CODES
    checks.append(
        QualityCheckResult(
            checkId="catalog.program_count",
            passed=programs_ok,
            severity="staging-blocker" if not programs_ok else "info",
            message=(
                f"Found {len(programs)} DDS programs (expected 3)."
                if programs_ok
                else f"Expected 3 DDS programs with codes {EXPECTED_PROGRAM_CODES}, found {program_codes}."
            ),
        )
    )
    if not programs_ok:
        add_finding(
            "catalog.program_count",
            "staging-blocker",
            "catalog_structure",
            "DDS staging programs missing or incorrect.",
            {"found": program_codes},
        )

    credits_ok = all(doc.get("totalCredits") == EXPECTED_TOTAL_CREDITS for doc in programs)
    checks.append(
        QualityCheckResult(
            checkId="catalog.total_credits",
            passed=credits_ok,
            severity="staging-blocker" if not credits_ok else "info",
            message="All programs have totalCredits=155.0."
            if credits_ok
            else "One or more programs do not have totalCredits=155.0.",
        )
    )

    requirements_ok = len(requirements) == EXPECTED_REQUIREMENT_GROUPS
    checks.append(
        QualityCheckResult(
            checkId="catalog.requirement_groups",
            passed=requirements_ok,
            severity="staging-blocker" if not requirements_ok else "info",
            message=f"Found {len(requirements)} requirement groups (expected {EXPECTED_REQUIREMENT_GROUPS}).",
        )
    )
    if not requirements_ok and programs:
        add_finding(
            "catalog.requirement_groups",
            "warning" if len(requirements) > 0 else "staging-blocker",
            "catalog_structure",
            f"Requirement group count is {len(requirements)}, expected {EXPECTED_REQUIREMENT_GROUPS}.",
        )

    rules_ok = len(rules) == EXPECTED_CATALOG_RULES
    checks.append(
        QualityCheckResult(
            checkId="catalog.non_executable_rules",
            passed=rules_ok,
            severity="warning" if not rules_ok and rules else "info",
            message=f"Found {len(rules)} catalog rules (expected {EXPECTED_CATALOG_RULES}).",
        )
    )

    signoff_ok = bool(programs) and all(doc.get("signoffReview") for doc in programs)
    checks.append(
        QualityCheckResult(
            checkId="catalog.signoff_review",
            passed=signoff_ok,
            severity="staging-blocker" if not signoff_ok else "info",
            message="signoffReview metadata present on programs."
            if signoff_ok
            else "signoffReview metadata missing from staged programs.",
        )
    )
    if not signoff_ok and programs:
        add_finding(
            "catalog.signoff_review",
            "production-blocker",
            "catalog_metadata",
            "signoffReview metadata is required before production promotion design.",
        )

    curation_ok = bool(programs) and all(
        doc.get("curationStatus") == EXPECTED_CURATION_STATUS for doc in programs
    )
    checks.append(
        QualityCheckResult(
            checkId="catalog.curation_status",
            passed=curation_ok,
            severity="production-blocker" if not curation_ok and programs else "info",
            message=f"curationStatus is {EXPECTED_CURATION_STATUS}."
            if curation_ok
            else "curationStatus is not ready-for-staging-with-review-flags on all programs.",
        )
    )

    # --- Course staging ---
    courses_ok = len(courses) > 0
    checks.append(
        QualityCheckResult(
            checkId="courses.staging_records",
            passed=courses_ok,
            severity="staging-blocker" if not courses_ok else "info",
            message=f"Found {len(courses)} Technion staged courses."
            if courses_ok
            else "No Technion course records in staging_courses.",
        )
    )
    if not courses_ok:
        add_finding(
            "courses.missing",
            "staging-blocker",
            "course_staging",
            "staging_courses has no technion-course-json records. Run Phase 9 import.",
        )

    offerings_ok = len(offerings) > 0
    checks.append(
        QualityCheckResult(
            checkId="courses.offerings",
            passed=offerings_ok,
            severity="warning" if not offerings_ok and courses_ok else "info",
            message=f"Found {len(offerings)} staged course offerings.",
        )
    )

    prod_eligible_bad = [doc for doc in courses if doc.get("productionEligible") is not False]
    staging_flag_bad = [doc for doc in courses if doc.get("isStaging") is not True]
    inferred_bad = [
        doc
        for doc in courses
        if doc.get("metadata", {}).get("degreeRequirementsInferred") is not False
    ]
    checks.append(
        QualityCheckResult(
            checkId="courses.production_eligible_false",
            passed=not prod_eligible_bad,
            severity="production-blocker" if prod_eligible_bad else "info",
            message="All staged courses have productionEligible=false."
            if not prod_eligible_bad
            else f"{len(prod_eligible_bad)} staged courses have productionEligible!=false.",
        )
    )
    checks.append(
        QualityCheckResult(
            checkId="courses.is_staging_true",
            passed=not staging_flag_bad,
            severity="staging-blocker" if staging_flag_bad else "info",
            message="All staged courses have isStaging=true."
            if not staging_flag_bad
            else f"{len(staging_flag_bad)} staged courses missing isStaging=true.",
        )
    )
    checks.append(
        QualityCheckResult(
            checkId="courses.no_requirement_inference",
            passed=not inferred_bad,
            severity="production-blocker" if inferred_bad else "info",
            message="Course JSON metadata does not infer degree requirements."
            if not inferred_bad
            else "Some staged courses have degreeRequirementsInferred!=false.",
        )
    )

    # --- Cross-link ---
    course_refs = _collect_course_references(requirements)
    unique_ref_numbers = sorted(
        {ref.get("courseNumber") for ref in course_refs if ref.get("courseNumber")}
    )
    missing_in_courses = sorted(
        number for number in unique_ref_numbers if number not in staged_course_numbers
    )
    missing_excluded_from_production = sorted(
        number for number in missing_in_courses if number in production_excluded_courses
    )
    missing_actionable = sorted(
        number for number in missing_in_courses if number not in production_excluded_courses
    )
    covered = len(unique_ref_numbers) - len(missing_actionable)
    coverage_denominator = len(unique_ref_numbers) - len(missing_excluded_from_production)
    coverage_pct = (
        round((covered / coverage_denominator * 100), 2) if coverage_denominator else 100.0
    )

    ocr_suspects: list[dict[str, Any]] = []
    for number in missing_actionable:
        neighbors = find_ocr_suspect_neighbors(number, staged_course_numbers)
        entry = {"courseNumber": number, "neighborMatches": neighbors}
        ocr_suspects.append(entry)
        if number in KNOWN_OCR_SUSPECT_NUMBERS or neighbors:
            severity = "production-blocker"
            add_finding(
                f"crosslink.ocr_suspect.{number}",
                severity,
                "cross_link",
                f"Missing catalog course {number} may be OCR-corrupted."
                + (f" Nearby staged matches: {neighbors}" if neighbors else ""),
                entry,
            )

    checks.append(
        QualityCheckResult(
            checkId="crosslink.course_reference_coverage",
            passed=not missing_actionable,
            severity="warning" if missing_actionable else "info",
            message=(
                f"Course reference coverage {coverage_pct}% "
                f"({covered}/{coverage_denominator} in-scope referenced numbers in staging_courses)."
            ),
            details={
                "coveragePercent": coverage_pct,
                "referenced": len(unique_ref_numbers),
                "missing": missing_actionable[:50],
                "productionExcludedMissing": missing_excluded_from_production,
            },
        )
    )
    if missing_actionable:
        warnings.append(
            f"{len(missing_actionable)} catalog course references missing from staging_courses.",
        )
    if missing_excluded_from_production:
        add_finding(
            "crosslink.production_excluded_courses",
            "info",
            "cross_link",
            (
                f"{len(missing_excluded_from_production)} catalog course references are vault-signed "
                "production exclusions (not in 2025 JSON; omit from production)."
            ),
            {"courseNumbers": missing_excluded_from_production},
        )

    # --- Title hints ---
    missing_title_refs = [
        ref
        for ref in course_refs
        if not ref.get("titleHint") and COURSE_NUMBER_PATTERN.fullmatch(str(ref.get("courseNumber", "")))
    ]
    missing_title_actionable = [
        ref
        for ref in missing_title_refs
        if ref.get("courseNumber") not in production_excluded_courses
    ]
    missing_title_excluded = [
        ref
        for ref in missing_title_refs
        if ref.get("courseNumber") in production_excluded_courses
    ]
    fillable_from_courses: list[dict[str, str]] = []
    for ref in missing_title_refs:
        number = ref.get("courseNumber")
        staged = next((c for c in courses if c.get("courseNumber") == number), None)
        if staged and staged.get("titleHebrew"):
            fillable_from_courses.append(
                {
                    "courseNumber": number,
                    "titleHebrew": staged["titleHebrew"],
                    "groupId": ref.get("groupId", ""),
                }
            )

    if missing_title_actionable:
        warnings.append(
            f"{len(missing_title_actionable)} in-scope course references lack titleHint in catalog staging.",
        )
        add_finding(
            "titles.missing_title_hint",
            "production-blocker",
            "title_metadata",
            f"{len(missing_title_actionable)} catalog course references missing titleHint.",
            {"count": len(missing_title_actionable)},
        )
    elif missing_title_excluded and non_executable_signed_off:
        add_finding(
            "titles.missing_title_hint_excluded_only",
            "info",
            "title_metadata",
            (
                f"{len(missing_title_excluded)} production-excluded catalog references lack titleHint; "
                "vault sign-off allows reference-only metadata."
            ),
            {"count": len(missing_title_excluded), "courseNumbers": sorted(
                {ref.get("courseNumber") for ref in missing_title_excluded if ref.get("courseNumber")}
            )},
        )
    elif missing_title_refs:
        warnings.append(f"{len(missing_title_refs)} course references lack titleHint in catalog staging.")
    if fillable_from_courses:
        recommendations.append(
            f"{len(fillable_from_courses)} missing titleHints could be enriched from staging_courses "
            "during a future promotion pass (not applied in Phase 10).",
        )

    # --- Credit mismatches ---
    credit_mismatches: list[dict[str, Any]] = []
    for ref in course_refs:
        hint = ref.get("creditsHint")
        number = ref.get("courseNumber")
        if hint is None or not number:
            continue
        staged = next((c for c in courses if c.get("courseNumber") == number), None)
        if not staged or staged.get("credits") is None:
            continue
        staged_credits = float(staged["credits"])
        if abs(float(hint) - staged_credits) > 0.25:
            credit_mismatches.append(
                {
                    "courseNumber": number,
                    "creditsHint": hint,
                    "stagingCredits": staged_credits,
                    "groupId": ref.get("groupId"),
                }
            )
    if credit_mismatches:
        warnings.append(f"{len(credit_mismatches)} credit mismatches between catalog hints and staged courses.")
        add_finding(
            "credits.mismatch",
            "warning",
            "credit_metadata",
            f"{len(credit_mismatches)} creditsHint values differ from staging_courses credits.",
            {"sample": credit_mismatches[:20]},
        )

    # --- Rule checks ---
    executable_count = 0
    non_executable_requirement_groups: set[str] = set()
    chain_violations: list[str] = []
    for document in requirements:
        group = document.get("requirementGroup", {})
        rule = group.get("ruleExpression", {})
        rule_type = rule.get("type", "")
        group_id = group.get("groupId", "")
        if rule_type in EXECUTABLE_RULE_TYPES:
            executable_count += 1
        elif rule_type:
            non_executable_requirement_groups.add(group_id)
        is_chain = "chain" in group_id or "focus" in group_id
        is_track_pool = group_id.endswith(":track:requirements") or rule.get("type") == "track_requirement"
        treats_as_mandatory = document.get("treatsCoursesAsMandatory") is True
        if is_chain and treats_as_mandatory:
            chain_violations.append(group_id)
        if (
            not is_track_pool
            and (is_chain or rule.get("operator") == "choose_n")
            and group.get("courseReferences")
        ):
            if treats_as_mandatory or rule.get("operator") == "choose_n":
                chain_violations.append(f"{group_id}:flattened_courses")
    non_executable_catalog_rules = sum(1 for rule in rules if not rule.get("ruleIsExecutable"))
    executable_count += sum(1 for rule in rules if rule.get("ruleIsExecutable"))
    non_executable_count = len(non_executable_requirement_groups) + non_executable_catalog_rules
    for rule in rules:
        if rule.get("treatsCoursesAsMandatory"):
            chain_violations.append(rule.get("requirementGroupId", rule.get("stagingKey", "")))

    checks.append(
        QualityCheckResult(
            checkId="rules.non_executable_preserved",
            passed=not chain_violations,
            severity="production-blocker" if chain_violations else "info",
            message="IE/IS chain rules remain non-mandatory."
            if not chain_violations
            else f"{len(chain_violations)} chain/focus rule violations detected.",
            details={"violations": chain_violations[:20]},
        )
    )
    if non_executable_requirement_groups and not non_executable_signed_off:
        production_blockers.append(
            f"{len(non_executable_requirement_groups)} non-executable requirement groups "
            "require vault catalog sign-off before production.",
        )
        api_blockers.append(
            "API migration must expose non-executable rules as manual-review items or remain staging-only.",
        )
    elif non_executable_signed_off:
        add_finding(
            "rules.vault_signoff_advisory_only",
            "info",
            "rules",
            (
                f"{len(non_executable_requirement_groups)} non-executable requirement groups "
                "signed off as advisory-only (not mandatory enforcement)."
            ),
            {"groupIds": sorted(non_executable_requirement_groups)},
        )
        recommendations.append(
            "Non-executable rule groups are signed off for advisory use only; do not auto-enforce in production.",
        )

    manual_review_summary = _count_manual_review_items(programs, requirements, rules)

    # --- Production safety (read-only) ---
    production_counts: dict[str, int] = {}
    for name in sorted(PRODUCTION_COLLECTION_NAMES):
        production_counts[name] = database[name].count_documents({})
    production_has_data = {k: v for k, v in production_counts.items() if v > 0}
    checks.append(
        QualityCheckResult(
            checkId="production.collections_untouched",
            passed=not production_has_data,
            severity="staging-blocker" if production_has_data else "info",
            message="Production collections are empty."
            if not production_has_data
            else f"Production collections contain data: {production_has_data}",
            details=production_counts,
        )
    )
    if production_has_data:
        add_finding(
            "production.data_present",
            "warning",
            "production_safety",
            "Production collections are not empty (review only; no writes performed).",
            production_has_data,
        )

    # --- Recommendation ---
    staging_blockers = [f.message for f in findings if f.severity == "staging-blocker"]
    if staging_blockers or not programs_ok or not courses_ok:
        recommendation = "needs-staging-fixes"
        status = "needs-fixes"
        summary = "Staging data is incomplete or structurally invalid for cross-link review."
    elif production_blockers or missing_title_actionable or missing_actionable:
        recommendation = "ready-for-production-promotion-design"
        status = "pass-with-warnings"
        summary = (
            "Staged DDS catalog and course data are structurally present. "
            "Production promotion remains blocked pending vault metadata fixes."
        )
    elif non_executable_signed_off and production_excluded_courses:
        recommendation = "ready-for-production-promotion-design"
        status = "pass"
        summary = (
            "Vault wiki sign-off recorded: non-executable groups are advisory-only and "
            f"{len(production_excluded_courses)} cross-link gap courses are excluded from production."
        )
    else:
        recommendation = "ready-for-staging-review"
        status = "pass"
        summary = "Staged data passes core quality checks with no critical staging blockers."

    if non_executable_signed_off:
        recommendations.append(
            "Non-executable rule groups are signed off as advisory-only; do not mandatory-enforce in production.",
        )
    else:
        recommendations.append(
            "Do not promote to production until vault sign-off on non-executable rules and OCR-suspect numbers.",
        )
    recommendations.extend(
        [
            "Phase 10 does not modify staged records; use this report to design a promotion gate.",
            "Course JSON is offering evidence only — never infer degree requirements from it.",
        ]
    )

    return DdsStagingQualityReport(
        reportId=f"dds-staging-quality-{uuid.uuid4().hex[:12]}",
        sourceName=QUALITY_SOURCE_NAME,
        sourceType=QUALITY_SOURCE_TYPE,
        generatedAt=_utc_now_iso(),
        status=status,
        recommendation=recommendation,  # type: ignore[arg-type]
        summary=summary,
        counts={
            "programs": len(programs),
            "requirementGroups": len(requirements),
            "catalogRules": len(rules),
            "stagedCourses": len(courses),
            "stagedOfferings": len(offerings),
            "uniqueCatalogCourseReferences": len(unique_ref_numbers),
            "missingCatalogCourseReferences": len(missing_actionable),
            "productionExcludedCatalogCourseReferences": len(missing_excluded_from_production),
            "missingTitleHints": len(missing_title_actionable),
            "missingTitleHintsExcludedOnly": len(missing_title_excluded),
            "creditMismatches": len(credit_mismatches),
            "manualReviewRequiredItems": manual_review_summary["total"],
            "executableRuleGroups": executable_count,
            "nonExecutableRuleGroups": non_executable_count,
            "ocrSuspectMissingCourses": len(
                [item for item in ocr_suspects if item["courseNumber"] in KNOWN_OCR_SUSPECT_NUMBERS]
            ),
        },
        checks=checks,
        findings=findings,
        warnings=sorted(set(warnings)),
        blockersForProduction=sorted(set(production_blockers)),
        blockersForApiMigration=sorted(set(api_blockers)),
        recommendations=recommendations,
        manualReviewSummary=manual_review_summary,
        courseReferenceCoverage={
            "coveragePercent": coverage_pct,
            "referencedCourseNumbers": len(unique_ref_numbers),
            "coveredInStagingCourses": covered,
            "missingInStagingCourses": missing_actionable,
            "productionExcludedMissing": missing_excluded_from_production,
            "ocrSuspectMissing": ocr_suspects,
        },
        creditMismatchSummary={
            "mismatchCount": len(credit_mismatches),
            "mismatches": credit_mismatches[:50],
            "severity": "warning",
        },
        nonExecutableRuleSummary={
            "executableRuleGroups": executable_count,
            "nonExecutableRuleGroups": non_executable_count,
            "chainRuleViolations": chain_violations,
        },
        missingTitleHintSummary={
            "missingCount": len(missing_title_refs),
            "fillableFromStagingCourses": fillable_from_courses[:50],
            "severity": "production-blocker" if missing_title_refs else "info",
        },
        productionSafetySummary={
            "productionCollectionCounts": production_counts,
            "productionCollectionsWithData": production_has_data,
            "thisCommandWritesProduction": False,
        },
    )


def render_quality_report_markdown(report: DdsStagingQualityReport) -> str:
    lines = [
        "# DDS Staging Quality Report",
        "",
        f"Generated: {report.generatedAt}",
        f"Status: **{report.status}**",
        f"Recommendation: **{report.recommendation}**",
        "",
        "> Phase 10 report-only validation — no staged or production records were modified.",
        "",
        "## Summary",
        report.summary,
        "",
        "## Counts",
    ]
    for key, value in report.counts.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Checks"])
    for check in report.checks:
        mark = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{mark}] {check.checkId}: {check.message}")
    lines.extend(["", "## Production blockers"])
    if report.blockersForProduction:
        for item in report.blockersForProduction[:25]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")
    lines.extend(["", "## API migration blockers"])
    if report.blockersForApiMigration:
        for item in report.blockersForApiMigration[:25]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")
    lines.extend(["", "## Course reference coverage"])
    coverage = report.courseReferenceCoverage
    lines.append(f"- Coverage: {coverage.get('coveragePercent')}%")
    lines.append(f"- Missing in staging_courses: {len(coverage.get('missingInStagingCourses', []))}")
    lines.extend(["", "## Missing title hints"])
    lines.append(f"- Count: {report.missingTitleHintSummary.get('missingCount')}")
    lines.extend(["", "## Recommendations"])
    for item in report.recommendations:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Production safety",
            "- **No production writes occurred in this phase.**",
            f"- Production collections with data: {report.productionSafetySummary.get('productionCollectionsWithData') or 'none'}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_quality_report_files(
    report: DdsStagingQualityReport,
    *,
    json_path: Path,
    md_path: Path,
) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_quality_report_markdown(report), encoding="utf-8")
    return json_path, md_path


def write_staging_quality_audit(
    database: Database,
    report: DdsStagingQualityReport,
    settings: Settings,
) -> str:
    collection_name = settings.staging_data_quality_reports_collection
    assert_staging_collection_name(collection_name)
    staging_key = f"technion-dds:quality:{report.generatedAt}"
    document = {
        "stagingKey": staging_key,
        "sourceName": QUALITY_SOURCE_NAME,
        "sourceType": QUALITY_SOURCE_TYPE,
        "reportId": report.reportId,
        "generatedAt": report.generatedAt,
        "status": report.status,
        "recommendation": report.recommendation,
        "summary": report.summary,
        "counts": report.counts,
        "blockersForProduction": report.blockersForProduction,
        "isStaging": True,
        "productionEligible": False,
        "requiresHumanReview": True,
        "report": report.model_dump(mode="json"),
    }
    database[collection_name].update_one(
        {"stagingKey": staging_key},
        {"$set": document},
        upsert=True,
    )
    return staging_key


def run_dds_staging_quality_review(
    database: Database,
    *,
    settings: Settings | None = None,
    json_path: Path | None = None,
    md_path: Path | None = None,
    write_staging_audit: bool = False,
) -> DdsStagingQualityReport:
    settings = settings or get_settings()
    report = build_dds_staging_quality_report(database, settings)
    write_quality_report_files(
        report,
        json_path=json_path or default_json_report_path(),
        md_path=md_path or default_md_report_path(),
    )
    if write_staging_audit:
        write_staging_quality_audit(database, report, settings)
    return report
