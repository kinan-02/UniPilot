"""Phase 10.5 — staging blocker cleanup and curated catalog repairs (source-backed only)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.curation.dds_catalog_curator import default_reviewed_output_path
from app.importers.dds_catalog_staging_importer import default_readiness_path
from app.sources.technion_course_json_index import build_course_index, default_course_json_paths
from app.sources.technion_dds_catalog_pdf import service_root

CleanupAction = Literal["remove", "correct", "enrich_title", "rule_fix", "unchanged"]

MISSING_REFERENCE_CLASSIFICATIONS: dict[str, str] = {
    "00960226": "source-backed-valid-not-in-2025-json",
    "00960244": "source-backed-valid-not-in-2025-json",
    "00960251": "source-backed-valid-not-in-2025-json",
    "00960293": "source-backed-valid-not-in-2025-json",
    "00960311": "source-backed-valid-not-in-2025-json",
    "00960335": "source-backed-valid-not-in-2025-json",
    "00960351": "likely-ocr-or-retired-number",
    "00960470": "source-backed-valid-not-in-2025-json",
    "00970211": "source-backed-valid-not-in-2025-json",
    "00970280": "source-backed-valid-not-in-2025-json",
    "00970329": "source-backed-valid-not-in-2025-json",
    "00980312": "source-backed-valid-not-in-2025-json",
    "00980455": "source-backed-valid-not-in-2025-json",
    "01040030": "source-backed-valid-in-2025-json",
    "01340020": "source-backed-valid-not-in-2025-json",
    "01500411": "sample-schedule-artifact-removed",
    "02300401": "likely-ocr-artifact-removed",
    "02740300": "source-backed-valid-not-in-2025-json",
    "00906292": "duplicate-ocr-artifact-removed",
}

MARKDOWN_TITLE_HINTS: dict[str, str] = {
    "00970329": "אלגוריתמים הסתברותיים",
    "00970211": "פרוטוקולי רשת עמידים בתקלות",
    "00980312": "אופטימיזציה 2",
    "00980455": "סטטיסטיקה ותהליכים סטוכסטיים 2",
    "01340020": "גנטיקה כללית",
    "02740300": 'תורשת האדם ת"א',
}

REMOVALS: list[tuple[str, str, str]] = [
    (
        "009216-1-000:elective-ds-pool",
        "00906292",
        "Duplicate OCR digit run from corrupted 00960291 title; 00960291 already listed in pool.",
    ),
    (
        "009216-1-000:semester-2-matrix",
        "02300401",
        "Not present in DDS semester-2 source table (markdown lines 1991-1995); OCR artifact.",
    ),
    (
        "009216-1-000:semester-2-matrix",
        "01500411",
        "Course number not found in DDS catalog markdown; treated as sample-schedule parser artifact.",
    ),
    (
        "009009-1-000:semester-3-matrix",
        "01500411",
        "Course number not found in DDS catalog markdown; treated as sample-schedule parser artifact.",
    ),
]

COGNITION_TRACK_GROUP_ID = "009216-1-000:cognition-track:requirements"


@dataclass
class CleanupChange:
    action: CleanupAction
    groupId: str
    courseNumber: str | None = None
    previousCourseNumber: str | None = None
    correctionEvidence: str | None = None
    classification: str | None = None
    manualReviewRequired: bool = True
    details: str = ""


@dataclass
class BlockerCleanupResult:
    changes: list[CleanupChange] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    investigated: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    before_metrics: dict[str, Any] = field(default_factory=dict)
    after_metrics: dict[str, Any] = field(default_factory=dict)


def default_cleanup_report_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_staging_blocker_cleanup_report.md"


def default_quality_report_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_staging_quality_report.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _count_catalog_stats(document: dict[str, Any]) -> dict[str, Any]:
    unique_numbers: set[str] = set()
    missing_titles = 0
    manual_review = 0
    non_executable = 0
    executable = 0

    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            rule = group.get("ruleExpression", {})
            rule_type = rule.get("type", "")
            if rule_type in {"credit_bucket"}:
                executable += 1
            elif rule_type:
                non_executable += 1
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber")
                if number:
                    unique_numbers.add(number)
                if not ref.get("titleHint"):
                    missing_titles += 1
                if ref.get("manualReviewRequired", True):
                    manual_review += 1

    for rule in document.get("catalogRules", []):
        if rule.get("ruleIsExecutable"):
            executable += 1
        else:
            non_executable += 1

    return {
        "uniqueCourseNumbers": len(unique_numbers),
        "missingTitleHints": missing_titles,
        "manualReviewRequiredItems": manual_review,
        "executableRuleGroups": executable,
        "nonExecutableRuleGroups": non_executable,
    }


def _find_group(document: dict[str, Any], group_id: str) -> dict[str, Any] | None:
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            if group.get("groupId") == group_id:
                return group
    return None


def _remove_course_reference(
    document: dict[str, Any],
    group_id: str,
    course_number: str,
    evidence: str,
    changes: list[CleanupChange],
) -> bool:
    group = _find_group(document, group_id)
    if group is None:
        return False
    refs = group.get("courseReferences", [])
    kept = [ref for ref in refs if ref.get("courseNumber") != course_number]
    if len(kept) == len(refs):
        return False
    group["courseReferences"] = kept
    changes.append(
        CleanupChange(
            action="remove",
            groupId=group_id,
            courseNumber=course_number,
            previousCourseNumber=course_number,
            correctionEvidence=evidence,
            classification=MISSING_REFERENCE_CLASSIFICATIONS.get(course_number, "parser-artifact"),
            details=evidence,
        ),
    )
    return True


def _enrich_title_from_sources(
    ref: dict[str, Any],
    *,
    group_id: str,
    course_index: dict[str, Any],
    changes: list[CleanupChange],
) -> bool:
    if ref.get("titleHint"):
        return False
    number = ref.get("courseNumber")
    if not number:
        return False

    record = course_index.get(number)
    if record and record.titleHebrew:
        ref["titleHint"] = record.titleHebrew
        ref.setdefault("sourceEvidence", []).append(
            f"titleHint-phase10.5:courses_json:{','.join(record.sourceFiles)}",
        )
        if record.credits is not None and ref.get("creditsHint") is None:
            ref["creditsHint"] = record.credits
        if record.faculty and ref.get("facultyHint") is None:
            ref["facultyHint"] = record.faculty
        if record.semestersOffered:
            ref["semestersOffered"] = sorted(set(record.semestersOffered))
        ref["manualReviewRequired"] = True
        ref["confidence"] = "medium"
        changes.append(
            CleanupChange(
                action="enrich_title",
                groupId=group_id,
                courseNumber=number,
                correctionEvidence=f"Exact match in semester course JSON ({','.join(record.sourceFiles)})",
                classification="title-from-course-json",
                details=record.titleHebrew,
            ),
        )
        return True

    markdown_title = MARKDOWN_TITLE_HINTS.get(number)
    if markdown_title:
        ref["titleHint"] = markdown_title
        ref.setdefault("sourceEvidence", []).append("titleHint-phase10.5:dds_catalog_markdown")
        ref["manualReviewRequired"] = True
        ref["confidence"] = "medium"
        changes.append(
            CleanupChange(
                action="enrich_title",
                groupId=group_id,
                courseNumber=number,
                correctionEvidence="Title from DDS catalog markdown (Phase 10.5 cleanup)",
                classification="title-from-markdown",
                details=markdown_title,
            ),
        )
        return True
    return False


def fix_cognition_track_rule(document: dict[str, Any], changes: list[CleanupChange]) -> None:
    group = _find_group(document, COGNITION_TRACK_GROUP_ID)
    if group is None:
        return
    rule = group.get("ruleExpression", {})
    if rule.get("type") == "track_requirement" and rule.get("operator") == "credit_pool":
        return
    group["requirementType"] = "elective"
    group["ruleExpression"] = {
        "type": "track_requirement",
        "operator": "credit_pool",
        "chooseFromLists": True,
    }
    group.setdefault("notes", []).append(
        "Phase 10.5: cognition track courses are elective pool options, not flattened mandatory choose-N.",
    )
    group["manualReviewRequired"] = True
    group["confidence"] = "medium"
    changes.append(
        CleanupChange(
            action="rule_fix",
            groupId=COGNITION_TRACK_GROUP_ID,
            correctionEvidence="Track/focus elective modeled as credit_pool (matches math-analytics track pattern).",
            classification="non-mandatory-track-rule",
            details="Replaced choose_n with credit_pool to avoid mandatory flattening.",
        ),
    )


def investigate_missing_references(document: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    numbers: set[str] = set()
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber")
                if number:
                    numbers.add(number)
    for number in sorted(numbers):
        classification = MISSING_REFERENCE_CLASSIFICATIONS.get(number, "unknown-manual-review")
        lines.append(f"{number}: {classification}")
    return lines


def apply_blocker_cleanup(
    document: dict[str, Any],
    *,
    course_json_paths: list[Path] | None = None,
) -> BlockerCleanupResult:
    result = BlockerCleanupResult()
    result.before_metrics = _count_catalog_stats(document)
    result.investigated = investigate_missing_references(document)

    paths = [path for path in (course_json_paths or default_course_json_paths()) if path.exists()]
    course_index = build_course_index(paths)

    for group_id, course_number, evidence in REMOVALS:
        _remove_course_reference(document, group_id, course_number, evidence, result.changes)

    fix_cognition_track_rule(document, result.changes)

    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            group_id = group.get("groupId", "")
            for ref in group.get("courseReferences", []):
                _enrich_title_from_sources(
                    ref,
                    group_id=group_id,
                    course_index=course_index,
                    changes=result.changes,
                )

    for number, classification in MISSING_REFERENCE_CLASSIFICATIONS.items():
        if classification.startswith("unknown") or "artifact-removed" in classification:
            continue
        if any(change.courseNumber == number and change.action == "enrich_title" for change in result.changes):
            continue
        still_missing_title = any(
            ref.get("courseNumber") == number and not ref.get("titleHint")
            for program in document.get("programs", [])
            for group in program.get("requirementGroups", [])
            for ref in group.get("courseReferences", [])
        )
        if still_missing_title and number not in {c.courseNumber for c in result.changes if c.action == "remove"}:
            result.unresolved.append(
                f"{number}: {classification} — titleHint still missing; requires human review.",
            )

    result.after_metrics = _count_catalog_stats(document)
    return result


def update_cleanup_metadata(document: dict[str, Any], result: BlockerCleanupResult) -> None:
    curation = document.setdefault("curationMetadata", {})
    curation["curationStatus"] = "ready-for-staging-with-review-flags"
    known = curation.setdefault("knownLimitations", [])
    limitation = (
        "Phase 10.5 removed parser/OCR artifacts and enriched source-backed titles; "
        "courses not offered in 2025 JSON may still lack staging cross-links."
    )
    if limitation not in known:
        known.append(limitation)

    counts_after = curation.setdefault("countsAfter", {})
    counts_after.update(result.after_metrics)
    counts_after["phase10_5CleanupAt"] = _utc_now_iso()

    report = document.setdefault("curationReport", {})
    report["phase10_5Cleanup"] = {
        "cleanupAt": _utc_now_iso(),
        "changesApplied": len(result.changes),
        "canPromoteToProduction": False,
    }

    removed_numbers = sorted(
        {change.courseNumber for change in result.changes if change.action == "remove" and change.courseNumber},
    )
    for number in removed_numbers:
        note = f"Phase 10.5 removed invalid catalog reference {number}."
        curation.setdefault("unresolvedIssues", [])
        if note not in curation["unresolvedIssues"]:
            curation["unresolvedIssues"].append(note)

    signoff = document.setdefault("signoffReview", {})
    signoff["productionPromotionRecommendation"] = (
        "Do not promote to production until human signoff on chain rules, tracks, and remaining unresolved titles."
    )
    signoff.setdefault("unresolvedItems", [])
    for item in result.unresolved:
        if item not in signoff["unresolvedItems"]:
            signoff["unresolvedItems"].append(item)


def build_phase8_readiness_check(document: dict[str, Any], result: BlockerCleanupResult) -> dict[str, Any]:
    stats = result.after_metrics
    return {
        "canImportToStaging": True,
        "canPromoteToProduction": False,
        "blockingIssuesForStaging": [],
        "blockingIssuesForProduction": [
            "Human signoff required on IE/IS chain rules and DS tracks.",
            "Courses not offered in 2025 semester JSON may lack staging cross-links.",
            "Semester matrices are recommended schedules, not hard logic.",
            "Production promotion remains blocked after Phase 10.5 cleanup.",
        ],
        "warnings": [
            f"{stats.get('missingTitleHints', 0)} course references still lack titleHint.",
            f"{stats.get('nonExecutableRuleGroups', 0)} requirement groups use non-executable rule expressions.",
            "Phase 10.5 removed OCR/parser artifacts only when source evidence was strong.",
        ],
        "reviewStatus": "ready-for-staging-with-review-flags",
        "phase8Recommendation": (
            "Safe to import to staging with review flags preserved; "
            "non-executable chain/track rules require human validation before production use."
        ),
        "productionPromotionRecommendation": (
            "Do not promote to production until human signoff on chain rules, tracks, and unresolved titles."
        ),
        "phase10_5CleanupAt": _utc_now_iso(),
        "counts": {
            "programs": len(document.get("programs", [])),
            "requirementGroups": sum(
                len(program.get("requirementGroups", [])) for program in document.get("programs", [])
            ),
            "courseReferences": sum(
                len(group.get("courseReferences", []))
                for program in document.get("programs", [])
                for group in program.get("requirementGroups", [])
            ),
            "uniqueCourseNumbers": stats.get("uniqueCourseNumbers", 0),
            "missingTitleHints": stats.get("missingTitleHints", 0),
            "manualReviewRequiredItems": stats.get("manualReviewRequiredItems", 0),
            "executableRuleGroups": stats.get("executableRuleGroups", 0),
            "nonExecutableRuleGroups": stats.get("nonExecutableRuleGroups", 0),
        },
        "titlesFilledDuringPhase10_5": sum(1 for change in result.changes if change.action == "enrich_title"),
        "referencesRemovedDuringPhase10_5": sum(1 for change in result.changes if change.action == "remove"),
    }


def render_cleanup_report_markdown(
    result: BlockerCleanupResult,
    *,
    quality_before_path: Path | None = None,
) -> str:
    lines = [
        "# DDS Staging Blocker Cleanup Report (Phase 10.5)",
        "",
        f"Generated: {_utc_now_iso()}",
        "",
        "> Source-backed cleanup only — no production writes; staged MongoDB updated only via explicit re-import.",
        "",
        "## Summary",
        f"- Changes applied: {len(result.changes)}",
        f"- Unresolved items: {len(result.unresolved)}",
        f"- Warnings: {len(result.warnings)}",
        "",
        "## Before metrics",
    ]
    for key, value in result.before_metrics.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## After metrics")
    for key, value in result.after_metrics.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Changes applied")
    if not result.changes:
        lines.append("- None")
    for change in result.changes:
        lines.append(
            f"- **{change.action}** `{change.groupId}`"
            + (f" course `{change.courseNumber}`" if change.courseNumber else "")
            + f": {change.details or change.correctionEvidence or ''}",
        )
    lines.append("")
    lines.append("## Investigated classifications")
    for item in result.investigated:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Unresolved")
    if not result.unresolved:
        lines.append("- None beyond expected 2025 JSON gaps and manual-review chain rules.")
    for item in result.unresolved:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Production safety")
    lines.append("- **No production collection writes in Phase 10.5.**")
    lines.append("- `canPromoteToProduction` remains **false**.")
    if quality_before_path and quality_before_path.exists():
        lines.append(f"- Prior quality report: `{quality_before_path}`")
    lines.append("")
    lines.append("## Phase 11 recommendation")
    lines.append(
        "Proceed to promotion-gate **design** after human review of this report; "
        "production promotion remains blocked.",
    )
    return "\n".join(lines) + "\n"


def run_blocker_cleanup(
    *,
    catalog_path: Path | None = None,
    readiness_path: Path | None = None,
    cleanup_report_path: Path | None = None,
    quality_before_path: Path | None = None,
    dry_run: bool = False,
    course_json_paths: list[Path] | None = None,
) -> dict[str, Any]:
    catalog_file = catalog_path or default_reviewed_output_path()
    readiness_file = readiness_path or default_readiness_path()
    report_file = cleanup_report_path or default_cleanup_report_path()
    quality_before = quality_before_path or default_quality_report_path()

    if not catalog_file.exists():
        raise FileNotFoundError(f"Curated catalog not found: {catalog_file}")

    payload = json.loads(catalog_file.read_text(encoding="utf-8"))
    result = apply_blocker_cleanup(payload, course_json_paths=course_json_paths)
    update_cleanup_metadata(payload, result)
    readiness = build_phase8_readiness_check(payload, result)
    report_md = render_cleanup_report_markdown(result, quality_before_path=quality_before)

    if not dry_run:
        catalog_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        readiness_file.write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report_md, encoding="utf-8")

    return {
        "dryRun": dry_run,
        "catalogPath": str(catalog_file),
        "readinessPath": str(readiness_file),
        "cleanupReportPath": str(report_file),
        "changesCount": len(result.changes),
        "unresolvedCount": len(result.unresolved),
        "beforeMetrics": result.before_metrics,
        "afterMetrics": result.after_metrics,
        "canPromoteToProduction": False,
        "changes": [
            {
                "action": change.action,
                "groupId": change.groupId,
                "courseNumber": change.courseNumber,
                "previousCourseNumber": change.previousCourseNumber,
                "correctionEvidence": change.correctionEvidence,
                "classification": change.classification,
            }
            for change in result.changes
        ],
        "unresolved": result.unresolved,
        "note": "Phase 10.5 cleanup — re-import staging catalog and re-run quality validation.",
    }
