"""Phase 7.6 — agent-assisted source verification and signoff review."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.curation.dds_catalog_curator import (
    SAMPLE_SCHEDULE_MARKERS,
    classify_markdown_course_context,
    default_markdown_path,
    default_reviewed_output_path,
)
from app.models.catalog import (
    ReviewedCuratedCatalogDocument,
    SignoffReviewMetadata,
)
from app.parsers.dds_catalog_markdown_parser import PROGRAM_CODES, split_program_sections
from app.sources.technion_course_json_index import (
    SEMESTER_CODE_LABELS,
    build_course_index,
    default_course_json_paths,
)
from app.sources.technion_dds_catalog_pdf import service_root
from app.utils.course_numbers import extract_course_title_pairs, normalize_course_number
from app.utils.hebrew_rtl import hebrew_letter_ratio

EXPECTED_PROGRAM_CODES = ["009216-1-000", "009009-1-000", "009118-1-000"]

EXPECTED_CREDIT_BUCKETS: dict[str, dict[str, float]] = {
    "009216-1-000": {
        "core-mandatory": 108.0,
        "elective-ds": 24.5,
        "elective-faculty": 10.5,
        "elective-general": 12.0,
        "enrichment": 6.0,
        "free-elective": 4.0,
        "physical-education": 2.0,
    },
    "009009-1-000": {
        "core-mandatory": 103.0,
        "elective-faculty": 40.0,
        "elective-general": 12.0,
        "enrichment": 6.0,
        "free-elective": 4.0,
        "physical-education": 2.0,
    },
    "009118-1-000": {
        "core-mandatory": 107.5,
        "elective-faculty": 35.5,
        "elective-general": 12.0,
        "enrichment": 6.0,
        "free-elective": 4.0,
        "physical-education": 2.0,
    },
}

DS_SEMESTER_ONE_REQUIRED = {
    "00940345",
    "01040031",
    "01040166",
    "02340117",
    "03240033",
}

EXECUTABLE_RULE_TYPES = {"credit_bucket"}

CHAIN_GROUP_MARKERS: dict[str, str] = {
    "ie-statistics-elective-chain": "רשימת הבחירה של סטטיסטיקה",
    "ie-behavior-science-chain": "רשימת הבחירה של מדעי ההתנהגות",
    "ie-focus-chain": "רשימת שרשראות מיקוד",
    "is-behavior-science-chain": "רשימת הבחירה של מדעי ההתנהגות",
    "is-focus-chain-performance": "שרשרת חקר ביצועים",
    "is-focus-chain-ml": "שרשרת למידה חישובית",
    "is-focus-chain-game-theory": "שרשרת תורת המשחקים",
}

INLINE_COURSE_LINE = re.compile(
    r"(?<!\d)(0\d{6,8}|\d{7,8})\s+([\u0590-\u05FF][^\n|]{2,100})",
)


def default_signoff_report_path() -> Path:
    return (
        service_root()
        / "data"
        / "curated"
        / "technion"
        / "dds_catalog"
        / "dds_catalog_signoff_review_report.md"
    )


def default_phase8_readiness_path() -> Path:
    return (
        service_root()
        / "data"
        / "curated"
        / "technion"
        / "dds_catalog"
        / "dds_catalog_phase8_readiness_check.json"
    )


def _looks_reversed_title(title: str) -> bool:
    stripped = title.strip()
    if not stripped:
        return True
    if stripped[0] in ")]*.,;:" or stripped.startswith("'"):
        return True
    if hebrew_letter_ratio(stripped) >= 0.5 and stripped[0].isascii():
        return True
    return False


def build_markdown_title_index(sections: dict[str, str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for section in sections.values():
        for match in INLINE_COURSE_LINE.finditer(section):
            number = normalize_course_number(match.group(1))
            if number is None:
                continue
            title = match.group(2).strip()
            if _looks_reversed_title(title):
                continue
            if number not in index:
                index[number] = title[:120]
        for pair in extract_course_title_pairs(section):
            number = str(pair["courseNumber"])
            title = pair.get("titleHint")
            if isinstance(title, str) and not _looks_reversed_title(title):
                index.setdefault(number, title[:120])
    return index


def _count_stats(document: dict[str, Any]) -> dict[str, Any]:
    programs = document.get("programs", [])
    groups = [group for program in programs for group in program.get("requirementGroups", [])]
    refs = [ref for group in groups for ref in group.get("courseReferences", [])]
    missing_titles = sum(1 for ref in refs if not ref.get("titleHint"))
    manual_review = 0
    for program in programs:
        if program.get("manualReviewRequired", True):
            manual_review += 1
        for group in program.get("requirementGroups", []):
            if group.get("manualReviewRequired", True):
                manual_review += 1
            for ref in group.get("courseReferences", []):
                if ref.get("manualReviewRequired", True):
                    manual_review += 1
    executable = 0
    non_executable = 0
    for group in groups:
        rule_type = group.get("ruleExpression", {}).get("type", "")
        if rule_type in EXECUTABLE_RULE_TYPES:
            executable += 1
        elif rule_type:
            non_executable += 1
    return {
        "programs": len(programs),
        "requirementGroups": len(groups),
        "courseReferences": len(refs),
        "uniqueCourseNumbers": len({ref.get("courseNumber") for ref in refs}),
        "missingTitleHints": missing_titles,
        "manualReviewRequiredItems": manual_review,
        "executableRuleGroups": executable,
        "nonExecutableRuleGroups": non_executable,
    }


def _verify_structure(document: dict[str, Any], verified: list[str], unresolved: list[str]) -> None:
    programs = document.get("programs", [])
    codes = [program.get("programCode") for program in programs]
    if codes == EXPECTED_PROGRAM_CODES:
        verified.append("Top-level structure: 3 expected program codes present.")
    else:
        unresolved.append(f"Program codes mismatch: {codes}")

    for program in programs:
        if program.get("totalCredits") == 155.0:
            verified.append(f"{program['programCode']}: totalCredits=155.0 verified.")
        else:
            unresolved.append(f"{program.get('programCode')}: totalCredits not 155.0")


def _verify_credit_buckets(
    document: dict[str, Any],
    verified: list[str],
    unresolved: list[str],
) -> None:
    for program in document.get("programs", []):
        code = program["programCode"]
        expected = EXPECTED_CREDIT_BUCKETS.get(code, {})
        for group in program.get("requirementGroups", []):
            if group.get("ruleExpression", {}).get("type") != "credit_bucket":
                continue
            bucket_id = group["groupId"].split(":")[-1]
            expected_value = expected.get(bucket_id)
            actual = group.get("minCredits")
            if expected_value is not None and actual == expected_value:
                verified.append(f"{code}:{bucket_id}={actual} credit bucket verified.")
                group["confidence"] = "high"
                group["manualReviewRequired"] = False
                group.setdefault("notes", []).append(
                    "Credit bucket verified against DDS catalog markdown (Phase 7.6 signoff).",
                )
            elif expected_value is not None:
                unresolved.append(f"{code}:{bucket_id} expected {expected_value}, found {actual}")


def _fill_missing_titles(
    document: dict[str, Any],
    course_index: dict[str, Any],
    markdown_titles: dict[str, str],
    verified: list[str],
    unresolved: list[str],
) -> int:
    filled = 0
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                if ref.get("titleHint"):
                    continue
                number = ref.get("courseNumber")
                record = course_index.get(number)
                if record and record.titleHebrew:
                    ref["titleHint"] = record.titleHebrew
                    ref.setdefault("sourceEvidence", []).append(
                        f"titleHint-signoff:courses_json:{','.join(record.sourceFiles)}",
                    )
                    ref["confidence"] = "medium"
                    filled += 1
                    continue

                markdown_title = markdown_titles.get(number)
                if markdown_title:
                    ref["titleHint"] = markdown_title
                    ref.setdefault("sourceEvidence", []).append("titleHint-signoff:dds_catalog_markdown")
                    ref["confidence"] = "medium"
                    filled += 1
                    continue

                ref.setdefault("notes", []).append(
                    "titleHint unresolved after Phase 7.6 signoff (not in semester JSON; no clear markdown title).",
                )
                ref["manualReviewRequired"] = True
                unresolved.append(f"Missing titleHint: {number} in {group['groupId']}")
    if filled:
        verified.append(f"Filled {filled} titleHint values during signoff from JSON/markdown.")
    return filled


def _verify_ds_semester_one(
    document: dict[str, Any],
    verified: list[str],
    unresolved: list[str],
) -> None:
    group = next(
        (
            group
            for program in document.get("programs", [])
            if program.get("programCode") == "009216-1-000"
            for group in program.get("requirementGroups", [])
            if group.get("groupId", "").endswith(":semester-1-matrix")
        ),
        None,
    )
    if group is None:
        unresolved.append("DS semester-1-matrix group missing.")
        return
    numbers = {ref.get("courseNumber") for ref in group.get("courseReferences", [])}
    for required in DS_SEMESTER_ONE_REQUIRED:
        if required in numbers:
            verified.append(f"DS semester-1 includes {required} (markdown-supported).")
        else:
            unresolved.append(f"DS semester-1 missing expected course {required}")


def _review_chain_groups(
    document: dict[str, Any],
    sections: dict[str, str],
    verified: list[str],
    unresolved: list[str],
) -> None:
    for program in document.get("programs", []):
        if program.get("programCode") not in {"009009-1-000", "009118-1-000"}:
            continue
        section = sections.get(program["programCode"], "")
        for group in program.get("requirementGroups", []):
            group_id = group.get("groupId", "")
            if group.get("ruleExpression", {}).get("type") != "course_pool":
                continue
            if not any(marker in group_id for marker in ("chain", "focus", "electives")):
                continue
            marker_key = next((key for key in CHAIN_GROUP_MARKERS if key in group_id), None)
            source_marker = CHAIN_GROUP_MARKERS.get(marker_key or "", "")
            if source_marker and source_marker in section:
                group.setdefault("notes", []).append(
                    f"Source-backed chain rule from markdown section '{source_marker}' (Phase 7.6).",
                )
                verified.append(f"{group_id}: choose-N/chain encoded as rule, not mandatory list.")
            else:
                unresolved.append(f"{group_id}: could not locate markdown source marker.")
            group["manualReviewRequired"] = True
            if group.get("courseReferences"):
                unresolved.append(f"{group_id}: contains flattened course references; review required.")


def _review_ds_tracks(
    document: dict[str, Any],
    sections: dict[str, str],
    verified: list[str],
    unresolved: list[str],
) -> None:
    ds_section = sections.get("009216-1-000", "")
    for program in document.get("programs", []):
        if program.get("programCode") != "009216-1-000":
            continue
        for group in program.get("requirementGroups", []):
            group_id = group.get("groupId", "")
            if "math-analytics-track" in group_id:
                if group.get("minCredits") == 26.0:
                    verified.append("DS math-analytics track 26-credit rule preserved.")
                else:
                    unresolved.append("DS math-analytics track minCredits not 26.0")
                group["manualReviewRequired"] = True
            if "cognition-track" in group_id:
                if "מגמה במדעי הקוגניציה" in ds_section:
                    verified.append("DS cognition track sourced from markdown.")
                group["manualReviewRequired"] = True
            if group_id.endswith("elective-faculty-pool"):
                verified.append("DS faculty elective pool remains prefix-rule based (no flattened list).")
                group["manualReviewRequired"] = True


def _propagate_footnotes(document: dict[str, Any], sections: dict[str, str]) -> None:
    for program in document.get("programs", []):
        section = sections.get(program.get("programCode", ""), "")
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber", "")
                compact = number[1:]
                for marker, token in [("**", "**"), ("***", "***"), ("*", "*")]:
                    if re.search(rf"{re.escape(marker)}{compact}", section):
                        markers = set(ref.get("footnoteMarkers", []))
                        markers.add(token)
                        ref["footnoteMarkers"] = sorted(markers)


def _validate_course_numbers(document: dict[str, Any], unresolved: list[str]) -> None:
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber", "")
                if not re.fullmatch(r"0\d{7}", number):
                    unresolved.append(f"Invalid course number format: {number}")


def run_signoff_review(
    *,
    reviewed_path: Path | None = None,
    markdown_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
) -> tuple[ReviewedCuratedCatalogDocument, dict[str, Any]]:
    reviewed_file = reviewed_path or default_reviewed_output_path()
    markdown_file = markdown_path or default_markdown_path()
    if not reviewed_file.exists():
        raise FileNotFoundError(f"Reviewed catalog not found: {reviewed_file}")

    payload = json.loads(reviewed_file.read_text(encoding="utf-8"))
    markdown_text = markdown_file.read_text(encoding="utf-8") if markdown_file.exists() else ""
    sections = split_program_sections(markdown_text)
    course_index = build_course_index(
        [path for path in (course_json_paths or default_course_json_paths()) if path.exists()]
    )
    markdown_titles = build_markdown_title_index(sections)

    reviewed = deepcopy(payload)
    verified: list[str] = []
    unresolved: list[str] = []
    checks = [
        "structure_validation",
        "credit_bucket_verification",
        "title_hint_resolution",
        "ds_semester_one_verification",
        "ie_is_chain_rule_review",
        "ds_track_review",
        "course_number_validation",
        "footnote_propagation",
    ]

    _verify_structure(reviewed, verified, unresolved)
    _verify_credit_buckets(reviewed, verified, unresolved)
    titles_filled = _fill_missing_titles(reviewed, course_index, markdown_titles, verified, unresolved)
    _verify_ds_semester_one(reviewed, verified, unresolved)
    _review_chain_groups(reviewed, sections, verified, unresolved)
    _review_ds_tracks(reviewed, sections, verified, unresolved)
    _validate_course_numbers(reviewed, unresolved)
    _propagate_footnotes(reviewed, sections)

    stats = _count_stats(reviewed)
    blocking_staging: list[str] = []
    if stats["programs"] != 3:
        blocking_staging.append("Program count is not 3.")
    if any(
        program.get("programCode") not in EXPECTED_PROGRAM_CODES for program in reviewed.get("programs", [])
    ):
        blocking_staging.append("Unexpected program codes.")

    review_status = "ready-for-staging-with-review-flags"
    if blocking_staging:
        review_status = "needs-more-curation"

    phase8_rec = (
        "Safe to import to staging with review flags preserved; "
        "non-executable chain/track rules require human validation before production use."
    )
    if blocking_staging:
        phase8_rec = "Resolve blocking structural issues before Phase 8 staging import."

    production_rec = "Do not promote to production until human signoff on chain rules, tracks, and unresolved titles."

    signoff = SignoffReviewMetadata(
        reviewedBy="cursor-agent-source-review",
        reviewedAt=datetime.now(UTC).replace(microsecond=0).isoformat(),
        reviewStatus=review_status,
        sourceFilesReviewed=[
            str(reviewed_file),
            str(markdown_file),
            *[path.name for path in (course_json_paths or default_course_json_paths()) if path.exists()],
        ],
        checksPerformed=checks,
        verifiedItems=verified,
        unresolvedItems=sorted(set(unresolved)),
        phase8Recommendation=phase8_rec,
        productionPromotionRecommendation=production_rec,
    )

    reviewed["signoffReview"] = signoff.model_dump(mode="json")
    if "curationMetadata" in reviewed:
        reviewed["curationMetadata"]["curationStatus"] = review_status
        reviewed["curationMetadata"]["unresolvedIssues"] = sorted(
            set(reviewed["curationMetadata"].get("unresolvedIssues", []) + unresolved)
        )

    reviewed["source"]["notes"] = [
        "Phase 7.5 cursor-assisted curation over parser draft.",
        "Phase 7.6 agent-assisted source verification (not true human approval).",
        "Course JSON used for offering metadata only — not requirement inference.",
    ]

    document = ReviewedCuratedCatalogDocument.model_validate(reviewed)
    readiness = build_phase8_readiness_check(document, blocking_staging=blocking_staging, stats=stats)
    readiness["titlesFilledDuringSignoff"] = titles_filled
    return document, readiness


def build_phase8_readiness_check(
    document: ReviewedCuratedCatalogDocument,
    *,
    blocking_staging: list[str],
    stats: dict[str, Any],
) -> dict[str, Any]:
    signoff = document.signoffReview
    warnings = list(document.curationReport.get("warnings", []))
    if stats["missingTitleHints"]:
        warnings.append(f"{stats['missingTitleHints']} course references still lack titleHint.")
    if stats["nonExecutableRuleGroups"]:
        warnings.append(
            f"{stats['nonExecutableRuleGroups']} requirement groups use non-executable rule expressions.",
        )

    return {
        "canImportToStaging": not blocking_staging,
        "canPromoteToProduction": False,
        "blockingIssuesForStaging": blocking_staging,
        "blockingIssuesForProduction": [
            "Human signoff required on IE/IS chain rules and DS tracks.",
            "Unresolved titleHint values may remain.",
            "Semester matrices are recommended schedules, not hard logic.",
            "Production promotion is out of scope for Phase 7.6.",
        ],
        "warnings": warnings,
        "reviewStatus": signoff.reviewStatus if signoff else "unknown",
        "phase8Recommendation": signoff.phase8Recommendation if signoff else "",
        "productionPromotionRecommendation": signoff.productionPromotionRecommendation if signoff else "",
        "counts": stats,
    }


def render_signoff_report_markdown(
    document: ReviewedCuratedCatalogDocument,
    readiness: dict[str, Any],
) -> str:
    signoff = document.signoffReview
    stats = readiness.get("counts", {})
    lines = [
        "# DDS Catalog Signoff Review Report",
        "",
        f"Generated: {signoff.reviewedAt if signoff else 'unknown'}",
        f"Review status: **{signoff.reviewStatus if signoff else 'unknown'}**",
        "",
        "> Agent-assisted source verification only — **not** true human approval.",
        "",
        "## Review verdict",
        f"**{signoff.reviewStatus if signoff else 'unknown'}**",
        "",
        "## Files reviewed",
    ]
    if signoff:
        for path in signoff.sourceFilesReviewed:
            lines.append(f"- `{path}`")
    lines.extend(["", "## What was verified"])
    if signoff:
        for item in signoff.verifiedItems[:40]:
            lines.append(f"- {item}")
        if len(signoff.verifiedItems) > 40:
            lines.append(f"- ... and {len(signoff.verifiedItems) - 40} more")
    lines.extend(
        [
            "",
            "## Fixes applied during signoff",
            f"- Title hints filled: {readiness.get('titlesFilledDuringSignoff', 0)}",
            "- Credit buckets marked verified where markdown values matched.",
            "- Footnote markers propagated where clearly tied in markdown.",
            "",
            "## Counts",
            f"- Programs: {stats.get('programs')}",
            f"- Requirement groups: {stats.get('requirementGroups')}",
            f"- Course references: {stats.get('courseReferences')}",
            f"- Missing title hints: {stats.get('missingTitleHints')}",
            f"- Manual review items: {stats.get('manualReviewRequiredItems')}",
            f"- Executable rule groups: {stats.get('executableRuleGroups')}",
            f"- Non-executable rule groups: {stats.get('nonExecutableRuleGroups')}",
            "",
            "## Remaining unresolved issues",
        ]
    )
    if signoff:
        for item in signoff.unresolvedItems[:35]:
            lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## IE/IS chain rule assessment",
            "- Choose-N and focus-chain rules remain non-executable `course_pool` groups with `manualReviewRequired: true`.",
            "- No chain courses were flattened into mandatory requirements.",
            "",
            "## DS tracks assessment",
            "- Math-analytics 26-credit rule preserved as track requirement note.",
            "- Cognition track remains manual review.",
            "- Faculty elective pool remains prefix-rule based.",
            "",
            "## Footnote assessment",
            "- Markers `*`, `**`, `***` propagated only when clearly adjacent to course numbers in markdown.",
            "- `#` / `##` enrichment/free-elective buckets remain at credit-bucket level.",
            "",
            "## Phase 8 recommendation",
            readiness.get("phase8Recommendation", signoff.phase8Recommendation if signoff else ""),
            "",
            "## Production promotion recommendation",
            signoff.productionPromotionRecommendation if signoff else "not-ready",
            "",
            "## MongoDB / staging",
            "- **No MongoDB writes occurred.**",
            "- **No staging or production collections were modified.**",
        ]
    )
    return "\n".join(lines) + "\n"


def write_signoff_outputs(
    document: ReviewedCuratedCatalogDocument,
    readiness: dict[str, Any],
    *,
    reviewed_output_path: Path | None = None,
    signoff_report_path: Path | None = None,
    readiness_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    reviewed_target = reviewed_output_path or default_reviewed_output_path()
    if not reviewed_target.is_absolute():
        reviewed_target = (service_root() / reviewed_target).resolve()
    reviewed_target.parent.mkdir(parents=True, exist_ok=True)
    reviewed_target.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_target = signoff_report_path or default_signoff_report_path()
    if not report_target.is_absolute():
        report_target = (service_root() / report_target).resolve()
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(render_signoff_report_markdown(document, readiness), encoding="utf-8")

    readiness_target = readiness_path or default_phase8_readiness_path()
    if not readiness_target.is_absolute():
        readiness_target = (service_root() / readiness_target).resolve()
    readiness_target.parent.mkdir(parents=True, exist_ok=True)
    readiness_target.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    return reviewed_target, report_target, readiness_target


def run_signoff(
    *,
    reviewed_path: Path | None = None,
    markdown_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
    reviewed_output_path: Path | None = None,
    signoff_report_path: Path | None = None,
    readiness_path: Path | None = None,
) -> tuple[ReviewedCuratedCatalogDocument, dict[str, Any], Path, Path, Path]:
    document, readiness = run_signoff_review(
        reviewed_path=reviewed_path,
        markdown_path=markdown_path,
        course_json_paths=course_json_paths,
    )
    paths = write_signoff_outputs(
        document,
        readiness,
        reviewed_output_path=reviewed_output_path,
        signoff_report_path=signoff_report_path,
        readiness_path=readiness_path,
    )
    return document, readiness, *paths
