"""Phase 7.5 — assisted manual curation of DDS catalog draft using course JSON references."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.catalog import (
    CurationMetadata,
    ReviewedCuratedCatalogDocument,
)
from app.parsers.dds_catalog_markdown_parser import PROGRAM_CODES, split_program_sections
from app.sources.technion_course_json_index import (
    CourseOfferingRecord,
    SEMESTER_CODE_LABELS,
    build_course_index,
    default_course_json_paths,
)
from app.sources.technion_dds_catalog_pdf import service_root
from app.utils.course_numbers import extract_course_title_pairs, normalize_course_number

OFFERING_METADATA_NOTE = (
    "Semester offering JSON reference only; not the full canonical catalog."
)

SAMPLE_SCHEDULE_MARKERS = [
    "שנה א' - סמסטר",
    "שנה ב' - סמסטר",
    "שנה ג' - סמסטר",
    "שנה ד' - סמסטר",
    "שנה ה' - סמסטר",
    "ריכוז נקודות לפי סמסטרים",
    "תכנית לימודים לתואר כפול",
]

DS_SEMESTER_ONE_BLOCK_END = re.compile(
    r"^קורסי בחירה בהנדסת נתונים ומידע\s+(?:0\d{6,8}|\d{7,8})",
    flags=re.MULTILINE,
)

REQUIREMENT_SECTION_MARKERS = [
    "קורסי חובה - שיבוץ מומלץ",
    "קורסי בחירה בהנדסת נתונים ומידע",
    "קורסי בחירה פקולטית",
    "מגמה במדעי הקוגניציה",
    "מגמת אנליזה מתמטית",
    "רשימת הבחירה של סטטיסטיקה",
    "רשימת הבחירה של מדעי ההתנהגות",
    "רשימת שרשראות מיקוד",
    "שרשרת חקר ביצועים",
    "שרשרת למידה חישובית",
    "שרשרת תורת המשחקים",
]


def default_draft_path() -> Path:
    return (
        service_root()
        / "data"
        / "generated"
        / "technion"
        / "dds_catalog"
        / "dds_catalog_curated_draft.json"
    )


def default_markdown_path() -> Path:
    return (
        service_root()
        / "data"
        / "raw"
        / "technion"
        / "technion_dds_catalog_from_docx_clean.md"
    )


def default_reviewed_output_path() -> Path:
    return (
        service_root()
        / "data"
        / "curated"
        / "technion"
        / "dds_catalog"
        / "dds_catalog_curated_reviewed.json"
    )


def default_review_report_path() -> Path:
    return (
        service_root()
        / "data"
        / "curated"
        / "technion"
        / "dds_catalog"
        / "dds_catalog_curated_review_report.md"
    )


def _count_document_stats(document: dict[str, Any]) -> dict[str, Any]:
    programs = document.get("programs", [])
    groups = [group for program in programs for group in program.get("requirementGroups", [])]
    refs = [ref for group in groups for ref in group.get("courseReferences", [])]
    missing_titles = sum(1 for ref in refs if not ref.get("titleHint"))
    manual_review = sum(
        1
        for program in programs
        for group in program.get("requirementGroups", [])
        for ref in group.get("courseReferences", [])
        if ref.get("manualReviewRequired", True)
    )
    manual_review += sum(1 for program in programs if program.get("manualReviewRequired", True))
    manual_review += sum(
        1
        for program in programs
        for group in program.get("requirementGroups", [])
        if group.get("manualReviewRequired", True)
    )
    return {
        "programs": len(programs),
        "requirementGroups": len(groups),
        "courseReferences": len(refs),
        "uniqueCourseNumbers": len({ref.get("courseNumber") for ref in refs}),
        "missingTitleHints": missing_titles,
        "manualReviewItems": manual_review,
    }


def _looks_reversed_title(title: str) -> bool:
    if not title:
        return False
    stripped = title.strip()
    if stripped and stripped[0] in ")]*.,;:":
        return True
    if stripped.startswith("*ם") or stripped.startswith("ם"):
        return True
    return False


def _enrich_course_reference(
    ref: dict[str, Any],
    index: dict[str, CourseOfferingRecord],
    *,
    warnings: list[str],
) -> dict[str, Any]:
    enriched = deepcopy(ref)
    number = enriched.get("courseNumber")
    record = index.get(number)
    if record is None:
        if not enriched.get("titleHint"):
            enriched.setdefault("notes", []).append(
                "No matching semester offering JSON entry; title not inferred.",
            )
            enriched["manualReviewRequired"] = True
            enriched["confidence"] = "low"
        return enriched

    evidence_tag = ",".join(record.sourceFiles)
    if record.titleHebrew:
        current_title = enriched.get("titleHint")
        if not current_title or _looks_reversed_title(str(current_title)):
            enriched["titleHint"] = record.titleHebrew
            enriched.setdefault("sourceEvidence", []).append(
                f"titleHint:{evidence_tag}",
            )
            enriched["confidence"] = "medium"
        elif current_title != record.titleHebrew:
            enriched.setdefault("notes", []).append(
                f"Catalog title '{current_title}' differs from offering JSON '{record.titleHebrew}'.",
            )
            enriched["manualReviewRequired"] = True

    if record.credits is not None and enriched.get("creditsHint") is None:
        enriched["creditsHint"] = record.credits
        enriched.setdefault("sourceEvidence", []).append(
            f"creditsHint:{evidence_tag}",
        )

    if record.faculty:
        enriched["facultyHint"] = record.faculty
        enriched.setdefault("sourceEvidence", []).append(f"facultyHint:{evidence_tag}")
    if record.studyFramework and not enriched.get("facultyHint"):
        enriched["facultyHint"] = record.studyFramework
    if record.semestersOffered:
        enriched["semestersOffered"] = sorted(set(record.semestersOffered))
        enriched.setdefault("sourceEvidence", []).append(
            f"semestersOffered:{evidence_tag}",
        )
    if record.prerequisitesText:
        enriched["prerequisitesText"] = record.prerequisitesText
        enriched.setdefault("sourceEvidence", []).append(
            f"prerequisitesText:{evidence_tag}",
        )
    if record.corequisitesText:
        enriched["corequisitesText"] = record.corequisitesText
    if record.noAdditionalCreditText:
        enriched["noAdditionalCreditText"] = record.noAdditionalCreditText
    if record.syllabus:
        enriched.setdefault("notes", []).append(
            f"Syllabus excerpt available from offering JSON ({evidence_tag}).",
        )

    enriched["offeringMetadataNote"] = OFFERING_METADATA_NOTE
    if enriched.get("sourceEvidence"):
        enriched["sourceEvidence"] = sorted(set(enriched["sourceEvidence"]))

    if record.titleConflicts or record.creditsConflicts:
        enriched["manualReviewRequired"] = True
        enriched.setdefault("notes", []).append(
            "Conflicting offering JSON values: "
            + "; ".join(record.titleConflicts + record.creditsConflicts),
        )
        warnings.append(f"Offering JSON conflict for {number}")

    return enriched


def _course_ref_dict(
    number: str,
    *,
    title: str | None = None,
    notes: list[str] | None = None,
    semester: int | None = None,
) -> dict[str, Any]:
    return {
        "courseNumber": number,
        "titleHint": title,
        "creditsHint": None,
        "facultyHint": None,
        "semestersOffered": [],
        "prerequisitesText": None,
        "corequisitesText": None,
        "noAdditionalCreditText": None,
        "footnoteMarkers": [],
        "pageNumbers": [semester] if semester is not None else [],
        "sourceEvidence": [],
        "notes": notes or [],
        "manualReviewRequired": True,
        "confidence": "low",
        "offeringMetadataNote": OFFERING_METADATA_NOTE,
    }


def _existing_course_numbers(document: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                numbers.add(ref.get("courseNumber"))
    return numbers


def _find_group(document: dict[str, Any], program_code: str, group_suffix: str) -> dict[str, Any] | None:
    for program in document.get("programs", []):
        if program.get("programCode") != program_code:
            continue
        for group in program.get("requirementGroups", []):
            if group.get("groupId", "").endswith(group_suffix):
                return group
    return None


def _add_course_if_missing(
    group: dict[str, Any],
    number: str,
    *,
    title: str | None,
    notes: list[str],
    semester: int | None = None,
) -> bool:
    existing = {ref.get("courseNumber") for ref in group.get("courseReferences", [])}
    if number in existing:
        return False
    group.setdefault("courseReferences", []).append(
        _course_ref_dict(number, title=title, notes=notes, semester=semester),
    )
    return True


def extract_ds_semester_one_candidates(section: str) -> list[tuple[str, str | None]]:
    schedule_start = section.find("קורסי חובה - שיבוץ מומלץ לפי סמסטרים")
    scoped = section[schedule_start:] if schedule_start >= 0 else section
    match = re.search(r"^\s*סמסטר\s*1\s*$", scoped, flags=re.MULTILINE)
    if not match:
        return []
    tail = scoped[match.end() :]
    end = DS_SEMESTER_ONE_BLOCK_END.search(tail)
    block = tail[: end.start()] if end else tail[:1200]
    results: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for pair in extract_course_title_pairs(block):
        number = str(pair["courseNumber"])
        if number in seen:
            continue
        seen.add(number)
        title = pair.get("titleHint")
        if isinstance(title, str) and title.startswith("'"):
            title = None
        results.append((number, title))
    return results


def classify_markdown_course_context(section: str, number: str) -> str:
    for marker in SAMPLE_SCHEDULE_MARKERS:
        index = section.find(marker)
        if index >= 0 and number in section[index : index + 2500]:
            return "likely_sample_schedule"
    for marker in REQUIREMENT_SECTION_MARKERS:
        index = section.find(marker)
        if index >= 0 and number in section[index : index + 6000]:
            if "קורסי בחירה" in marker or "רשימת" in marker or "שרשרת" in marker:
                return "likely_elective_pool"
            if "שיבוץ" in marker or "סמסטר" in section[index : index + 500]:
                return "likely_mandatory"
            return "likely_requirement"
    if number in section:
        return "unknown_manual_review"
    return "not_in_program_section"


def add_ds_semester_one_courses(
    document: dict[str, Any],
    ds_section: str,
    *,
    added_numbers: list[str],
) -> None:
    group = _find_group(document, "009216-1-000", ":semester-1-matrix")
    if group is None:
        return
    for number, title in extract_ds_semester_one_candidates(ds_section):
        if _add_course_if_missing(
            group,
            number,
            title=title,
            notes=[
                "Added from DS semester-1 prose block in DDS catalog markdown.",
                "Recommended schedule metadata — verify mandatory vs elective markers.",
            ],
            semester=1,
        ):
            added_numbers.append(number)


def add_ie_chain_groups(document: dict[str, Any]) -> None:
    program = next(
        (p for p in document.get("programs", []) if p.get("programCode") == "009009-1-000"),
        None,
    )
    if program is None:
        return
    chains = [
        (
            "009009-1-000:ie-statistics-elective-chain",
            "IE statistics elective chain",
            "At least one course from the dedicated statistics elective list (40 faculty credits total).",
            {"type": "course_pool", "operator": "choose_n", "chooseCount": 1, "chain": "statistics"},
        ),
        (
            "009009-1-000:ie-behavior-science-chain",
            "IE behavior science elective chain",
            "At least one course from the behavior-science elective list.",
            {"type": "course_pool", "operator": "choose_n", "chooseCount": 1, "chain": "behavior_science"},
        ),
        (
            "009009-1-000:ie-focus-chain",
            "IE focus chain (3 courses)",
            "Complete at least one three-course focus chain per catalog markdown.",
            {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
        ),
        (
            "009009-1-000:ie-additional-faculty-electives",
            "IE additional faculty electives",
            "Remaining faculty elective credits from approved prefix lists; not flattened to mandatory courses.",
            {"type": "course_pool", "operator": "choose_credits", "allowedPrefixes": ["094", "095", "096", "097"]},
        ),
    ]
    existing_ids = {group.get("groupId") for group in program.get("requirementGroups", [])}
    for group_id, title, note, rule in chains:
        if group_id in existing_ids:
            continue
        program.setdefault("requirementGroups", []).append(
            {
                "groupId": group_id,
                "title": title,
                "requirementType": "elective",
                "minCredits": None,
                "courseReferences": [],
                "ruleExpression": rule,
                "pageNumbers": [],
                "notes": [note, "Encoded from IE faculty elective markdown; requires human verification."],
                "manualReviewRequired": True,
                "confidence": "low",
            }
        )


def add_is_chain_groups(document: dict[str, Any]) -> None:
    program = next(
        (p for p in document.get("programs", []) if p.get("programCode") == "009118-1-000"),
        None,
    )
    if program is None:
        return
    chains = [
        (
            "009118-1-000:is-behavior-science-chain",
            "IS behavior science elective chain",
            "At least one course from the behavior-science list.",
            {"type": "course_pool", "operator": "choose_n", "chooseCount": 1, "chain": "behavior_science"},
        ),
        (
            "009118-1-000:is-focus-chain-performance",
            "IS performance research focus chain",
            "Three-course focus chain per catalog markdown (performance research).",
            {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3, "chain": "performance_research"},
        ),
        (
            "009118-1-000:is-focus-chain-ml",
            "IS computational learning focus chain",
            "Three-course focus chain per catalog markdown (computational learning).",
            {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3, "chain": "computational_learning"},
        ),
        (
            "009118-1-000:is-focus-chain-game-theory",
            "IS game theory focus chain",
            "Three-course focus chain per catalog markdown (game theory and economic behavior).",
            {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3, "chain": "game_theory"},
        ),
        (
            "009118-1-000:is-additional-faculty-electives",
            "IS additional faculty electives",
            "Remaining faculty elective credits; courses with 094/095/096/097 prefixes per catalog.",
            {"type": "course_pool", "operator": "choose_credits", "allowedPrefixes": ["094", "095", "096", "097"]},
        ),
    ]
    existing_ids = {group.get("groupId") for group in program.get("requirementGroups", [])}
    for group_id, title, note, rule in chains:
        if group_id in existing_ids:
            continue
        program.setdefault("requirementGroups", []).append(
            {
                "groupId": group_id,
                "title": title,
                "requirementType": "elective",
                "minCredits": None,
                "courseReferences": [],
                "ruleExpression": rule,
                "pageNumbers": [],
                "notes": [note, "Encoded from IS faculty elective markdown; requires human verification."],
                "manualReviewRequired": True,
                "confidence": "low",
            }
        )


def enhance_ds_track_groups(document: dict[str, Any]) -> None:
    program = next(
        (p for p in document.get("programs", []) if p.get("programCode") == "009216-1-000"),
        None,
    )
    if program is None:
        return
    for group in program.get("requirementGroups", []):
        group_id = group.get("groupId", "")
        if group_id.endswith("math-analytics-track:requirements"):
            group["minCredits"] = 26.0
            group.setdefault("notes", []).append(
                "Catalog requires 26 credits from listed mathematical analytics track courses.",
            )
            group["ruleExpression"] = {
                "type": "track_requirement",
                "operator": "credit_pool",
                "minCredits": 26.0,
                "chooseFromLists": True,
            }
        if group_id.endswith("cognition-track:requirements"):
            group.setdefault("notes", []).append(
                "Cognition track includes project-heavy courses marked with * in catalog source.",
            )


def propagate_footnote_markers(ref: dict[str, Any], raw_text: str) -> None:
    number = ref.get("courseNumber", "")[1:].lstrip("0")
    compact = ref.get("courseNumber", "")[1:]
    patterns = [
        (r"\*" + compact, "*"),
        (r"\*\*" + compact, "**"),
        (r"\*\*\*" + compact, "***"),
    ]
    markers: list[str] = []
    for pattern, marker in patterns:
        if re.search(pattern, raw_text):
            markers.append(marker)
    if markers:
        ref["footnoteMarkers"] = sorted(set(markers))


def curate_dds_catalog(
    *,
    draft_path: Path | None = None,
    markdown_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
) -> tuple[ReviewedCuratedCatalogDocument, list[str]]:
    draft_file = draft_path or default_draft_path()
    markdown_file = markdown_path or default_markdown_path()
    if not draft_file.exists():
        raise FileNotFoundError(f"Draft curated catalog not found: {draft_file}")
    if not markdown_file.exists():
        raise FileNotFoundError(f"DDS catalog markdown not found: {markdown_file}")

    draft_payload = json.loads(draft_file.read_text(encoding="utf-8"))
    counts_before = _count_document_stats(draft_payload)
    markdown_text = markdown_file.read_text(encoding="utf-8")
    program_sections = split_program_sections(markdown_text)

    json_paths = course_json_paths if course_json_paths is not None else default_course_json_paths()
    json_paths = [path for path in json_paths if path.exists()]
    course_index = build_course_index(json_paths)

    reviewed = deepcopy(draft_payload)
    warnings: list[str] = []
    title_hints_filled = 0
    added_from_markdown: list[str] = []

    add_ds_semester_one_courses(reviewed, program_sections.get("009216-1-000", ""), added_numbers=added_from_markdown)
    add_ie_chain_groups(reviewed)
    add_is_chain_groups(reviewed)
    enhance_ds_track_groups(reviewed)

    for program in reviewed.get("programs", []):
        program_code = program.get("programCode", "")
        section = program_sections.get(program_code, "")
        for group in program.get("requirementGroups", []):
            enriched_refs: list[dict[str, Any]] = []
            for ref in group.get("courseReferences", []):
                before_title = ref.get("titleHint")
                enriched = _enrich_course_reference(ref, course_index, warnings=warnings)
                if section:
                    propagate_footnote_markers(enriched, section)
                if not before_title and enriched.get("titleHint"):
                    title_hints_filled += 1
                enriched_refs.append(enriched)
            group["courseReferences"] = enriched_refs

    draft_numbers = _existing_course_numbers(draft_payload)
    markdown_numbers: set[str] = set()
    classified_missing: dict[str, list[str]] = {
        "likely_mandatory": [],
        "likely_elective_pool": [],
        "likely_sample_schedule": [],
        "unknown_manual_review": [],
    }

    for program_code, section in program_sections.items():
        for raw in re.findall(r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)", section):
            normalized = normalize_course_number(raw)
            if normalized:
                markdown_numbers.add(normalized)

    for number in sorted(markdown_numbers - draft_numbers):
        program_code = next(
            (
                code
                for code, section in program_sections.items()
                if number.replace("0", "", 1) in section or number in section
            ),
            PROGRAM_CODES[0],
        )
        classification = classify_markdown_course_context(
            program_sections.get(program_code, ""),
            number,
        )
        key = classification if classification in classified_missing else "unknown_manual_review"
        classified_missing[key].append(number)

    counts_after = _count_document_stats(reviewed)
    remaining_missing_titles = counts_after["missingTitleHints"]

    reviewed["source"] = {
        **reviewed.get("source", {}),
        "sourceType": "dds_catalog_curated_reviewed",
        "sourceFile": str(markdown_file),
        "manualReviewRequired": True,
        "confidence": "medium",
        "notes": [
            "Phase 7.5 cursor-assisted curation over parser draft.",
            "Course JSON used for offering metadata only — not requirement inference.",
            "Requires human signoff before Phase 8 staging import.",
        ],
    }

    unresolved = [
        f"{len(classified_missing['unknown_manual_review'])} markdown course numbers remain unclassified.",
        f"{classified_missing['likely_sample_schedule'][:3]} ... sample-schedule-only numbers excluded.",
        f"{remaining_missing_titles} course references still lack titleHint after JSON enrichment.",
        "IE/IS choose-N chains encoded as rule groups without flattened mandatory courses.",
    ]

    curation_report = {
        "totalPrograms": counts_after["programs"],
        "totalRequirementGroups": counts_after["requirementGroups"],
        "totalCourseReferences": counts_after["courseReferences"],
        "titleHintsFilledFromCourseJson": title_hints_filled,
        "courseNumbersInMarkdown": len(markdown_numbers),
        "courseNumbersInDraft": len(draft_numbers),
        "courseNumbersAddedFromMarkdown": len(added_from_markdown),
        "courseNumbersAddedFromMarkdownList": added_from_markdown,
        "classifiedMissingFromMarkdown": {key: values[:25] for key, values in classified_missing.items()},
        "remainingMissingTitleHints": remaining_missing_titles,
        "remainingManualReviewItems": counts_after["manualReviewItems"],
        "warnings": warnings,
        "manualReviewRequired": True,
    }

    metadata = CurationMetadata(
        curatedBy="cursor-assisted",
        curatedAt=datetime.now(UTC).replace(microsecond=0).isoformat(),
        sourceDraftPath=str(draft_file),
        sourceMarkdownPath=str(markdown_file),
        courseJsonSources=[path.name for path in json_paths],
        curationStatus="draft-reviewed-needs-human-signoff",
        knownLimitations=[
            "Semester offering JSON is not the full canonical Technion catalog.",
            "Prerequisites/corequisites are reference metadata only, not degree logic.",
            "Choose-N and focus chains are encoded as notes/rules, not executable requirements.",
            "Sample 4-year schedule sections were not imported as requirements.",
        ],
        countsBefore=counts_before,
        countsAfter=counts_after,
        unresolvedIssues=unresolved,
    )

    document = ReviewedCuratedCatalogDocument.model_validate(
        {
            "source": reviewed["source"],
            "programs": reviewed["programs"],
            "parserReport": reviewed.get("parserReport", {}),
            "curationMetadata": metadata.model_dump(mode="json"),
            "curationReport": curation_report,
        }
    )
    return document, warnings


def write_reviewed_catalog(
    document: ReviewedCuratedCatalogDocument,
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or default_reviewed_output_path()
    if not target.is_absolute():
        target = (service_root() / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def render_review_report_markdown(document: ReviewedCuratedCatalogDocument) -> str:
    meta = document.curationMetadata
    report = document.curationReport
    lines = [
        "# DDS Catalog Curated Review Report",
        "",
        f"Generated: {meta.curatedAt}",
        f"Status: **{meta.curationStatus}**",
        "",
        "## Sources used",
        f"- Draft: `{meta.sourceDraftPath}`",
        f"- Markdown: `{meta.sourceMarkdownPath}`",
        "- Course JSON:",
    ]
    for source in meta.courseJsonSources:
        lines.append(f"  - `{source}`")
    lines.extend(
        [
            "",
            "## What was curated",
            "- Enriched existing draft course references with offering JSON metadata where exact course numbers matched.",
            "- Filled missing `titleHint` values from course JSON when available.",
            "- Added DS semester-1 courses from markdown prose block when absent from draft.",
            "- Added IE/IS faculty elective chain rule groups (choose-N, not flattened mandatory lists).",
            "- Preserved DS track rules and faculty prefix pools from parser output.",
            "",
            "## Counts",
            f"- Programs: {meta.countsBefore.get('programs')} → {meta.countsAfter.get('programs')}",
            f"- Requirement groups: {meta.countsBefore.get('requirementGroups')} → {meta.countsAfter.get('requirementGroups')}",
            f"- Course references: {meta.countsBefore.get('courseReferences')} → {meta.countsAfter.get('courseReferences')}",
            f"- Missing title hints: {meta.countsBefore.get('missingTitleHints')} → {meta.countsAfter.get('missingTitleHints')}",
            f"- Title hints filled from course JSON: {report.get('titleHintsFilledFromCourseJson')}",
            f"- Courses added from markdown: {report.get('courseNumbersAddedFromMarkdown')}",
            "",
            "## Course JSON enrichment",
            f"- Indexed semester codes: {', '.join(f'{code}={SEMESTER_CODE_LABELS.get(code, code)}' for code in sorted({200, 201, 202}))}",
            "- Enriched fields when matched: `titleHint`, `creditsHint`, `facultyHint`, `semestersOffered`, prerequisite/corequisite text.",
            "- Offering metadata is reference-only and flagged in each course reference.",
            "",
            "## Remaining uncertainties",
        ]
    )
    for issue in meta.unresolvedIssues:
        lines.append(f"- {issue}")
    if report.get("warnings"):
        lines.extend(["", "## Curation warnings"])
        for warning in report["warnings"][:30]:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "## Human verification still required",
            "- IE/IS focus chain course lists and choose-N counts.",
            "- DS semester matrices and elective pool completeness.",
            "- Footnote markers (`*`, `**`, `***`, `#`, `##`) per course.",
            "- Full signoff on all `manualReviewRequired` flags.",
            "",
            "## MongoDB / staging",
            "- **No MongoDB writes occurred.**",
            "- **No staging or production collections were modified.**",
            "",
            "## Phase 8 recommendation",
            "**Not ready** for automated Phase 8 staging import.",
            "Proceed only after human signoff on this reviewed JSON and spot-checking high-risk groups (chains, semester matrices, track rules).",
        ]
    )
    return "\n".join(lines) + "\n"


def run_curation(
    *,
    draft_path: Path | None = None,
    markdown_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
) -> tuple[ReviewedCuratedCatalogDocument, Path, Path]:
    document, _warnings = curate_dds_catalog(
        draft_path=draft_path,
        markdown_path=markdown_path,
        course_json_paths=course_json_paths,
    )
    reviewed_path = write_reviewed_catalog(document, output_path=output_path)
    report_target = report_path or default_review_report_path()
    if not report_target.is_absolute():
        report_target = (service_root() / report_target).resolve()
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(render_review_report_markdown(document), encoding="utf-8")
    return document, reviewed_path, report_target
