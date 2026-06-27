"""Export DDS catalog JSON from the catalog wiki vault."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.catalog import CatalogCourseReference, ReviewedCuratedCatalogDocument
from app.models.staging_catalog import Phase8ReadinessCheck
from app.paths import (
    catalog_vault_root,
    default_catalog_export_dir,
    default_catalog_reviewed_path,
    default_readiness_path,
    service_root,
)
from app.sources.technion_course_json_index import build_course_index, default_course_json_paths
from app.utils.course_numbers import (
    collect_course_numbers_from_text,
    normalize_course_number,
    resolve_course_number_token,
    title_hint_from_wikilink_cell,
)
from app.vault.loader import WikiPage, extract_field, load_pages_by_slug, wiki_root
from app.vault.markdown_tables import MarkdownTable, find_table_with_header, parse_markdown_tables
from app.vault.vault_signoff import apply_vault_signoff_to_catalog, build_readiness_after_vault_signoff
from app.vault.wiki_path_catalog import build_wiki_path_catalog

CATALOG_YEAR = 2025
CATALOG_VERSION = "2025-2026"
INSTITUTION_ID = "technion"

DDS_TRACK_SLUGS: dict[str, dict[str, Any]] = {
    "track-data-information-engineering": {
        "programCode": "009216-1-000",
        "nameEn": "Data and Information Engineering",
        "coreMandatoryCredits": 108.0,
        "creditBuckets": [
            ("Required courses", "core-mandatory", "core", 108.0),
            ("DNE electives", "elective-ds", "elective", 24.5),
            ("Faculty electives", "elective-faculty", "elective", 10.5),
            ("University enrichment", "enrichment", "enrichment", 6.0),
            ("Free electives", "free-elective", "elective", 4.0),
            ("Physical Education", "physical-education", "enrichment", 2.0),
        ],
        "electivePoolHeading": "DNE Elective Course List",
        "electivePoolGroupId": "elective-ds-pool",
        "facultyPoolGroupId": "elective-faculty-pool",
    },
    "track-industrial-engineering-management": {
        "programCode": "009009-1-000",
        "nameEn": "Industrial Engineering and Management",
        "coreMandatoryCredits": 103.0,
        "creditBuckets": [
            ("Required courses", "core-mandatory", "core", 103.0),
            ("Faculty electives", "elective-faculty", "elective", 40.0),
            ("University enrichment", "enrichment", "enrichment", 6.0),
            ("Free electives", "free-elective", "elective", 4.0),
            ("Physical Education", "physical-education", "enrichment", 2.0),
        ],
    },
    "track-information-systems-engineering": {
        "programCode": "009118-1-000",
        "nameEn": "Information Systems Engineering",
        "coreMandatoryCredits": 107.5,
        "creditBuckets": [
            ("Required courses", "core-mandatory", "core", 107.5),
            ("Faculty electives", "elective-faculty", "elective", 35.5),
            ("University enrichment", "enrichment", "enrichment", 6.0),
            ("Free electives", "free-elective", "elective", 4.0),
            ("Physical Education", "physical-education", "enrichment", 2.0),
        ],
    },
}

SEMESTER_HEADING_PATTERN = re.compile(
    r"^###\s+Semester\s+(\d+)\b.*$",
    re.MULTILINE | re.IGNORECASE,
)
COURSE_NUMBER_INLINE_PATTERN = re.compile(r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)")

# DNE electives marked * in the vault wiki (data-intensive project courses).
DNE_STARRED_COURSE_NUMBERS: tuple[str, ...] = (
    "0960222",
    "0960231",
    "0960235",
    "0960262",
    "0960324",
    "0960693",
    "0970135",
    "0970200",
    "0970215",
    "0970216",
    "0970222",
    "0970247",
    "0970248",
    "0970272",
    "0970400",
)

IS_BEHAVIOR_SCIENCE_CATALOG_DESCRIPTION = (
    "Group 1 — Behavioral sciences: choose at least one of the two listed courses."
)
IE_STATISTICS_CATALOG_DESCRIPTION = (
    "Group 1 — Statistics: choose at least one course from the statistics elective list."
)
IE_BEHAVIOR_SCIENCE_CATALOG_DESCRIPTION = (
    "Group 2 — Behavioral sciences: choose at least one course from the listed options."
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _relative_vault_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(service_root().resolve()))
    except ValueError:
        return str(path)


def parse_credits_value(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.replace("≈", "").strip()
    if not cleaned:
        return None
    range_match = re.match(r"^(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)", cleaned)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return round((low + high) / 2, 2)
    number_match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not number_match:
        return None
    return float(number_match.group(0))


def _column_index(headers: list[str], *candidates: str) -> int | None:
    lowered = [header.lower() for header in headers]
    for candidate in candidates:
        for index, header in enumerate(lowered):
            if candidate.lower() in header:
                return index
    return None


def _table_course_rows(
    table: MarkdownTable,
    *,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, str | None]]:
    code_idx = _column_index(table.headers, "code", "קוד")
    if code_idx is None:
        return []

    name_idx = _column_index(table.headers, "name", "course", "שם")
    credits_idx = _column_index(table.headers, "credit", "נ\"ז", "נז")
    notes_idx = _column_index(table.headers, "notes", "הערות")

    rows: list[dict[str, str | None]] = []
    for row in table.rows:
        if code_idx >= len(row):
            continue
        code = row[code_idx].strip()
        if not code or code.startswith("**") or "total" in code.lower():
            continue
        if resolve_course_number_token(code) is None:
            continue
        name_cell = row[name_idx].strip() if name_idx is not None and name_idx < len(row) else None
        title_hint = title_hint_from_wikilink_cell(code, fallback_name=name_cell, pages=pages)
        rows.append(
            {
                "code": code,
                "name": title_hint or name_cell,
                "credits": row[credits_idx].strip() if credits_idx is not None and credits_idx < len(row) else None,
                "notes": row[notes_idx].strip() if notes_idx is not None and notes_idx < len(row) else None,
            }
        )
    return rows


def _to_catalog_course_reference(ref: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields allowed by CatalogCourseReference (Pydantic export schema)."""
    allowed = CatalogCourseReference.model_fields.keys()
    payload = {key: ref[key] for key in allowed if key in ref}
    return CatalogCourseReference.model_validate(payload).model_dump(mode="json")


def build_course_reference(
    code: str,
    *,
    title_hint: str | None = None,
    credits_hint: float | None = None,
    credits_hint_raw: str | None = None,
    source_page: Path | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any] | None:
    course_number = resolve_course_number_token(code)
    if course_number is None:
        return None

    evidence: list[str] = []
    if source_page is not None:
        evidence.append(f"wiki:{_relative_vault_path(source_page)}")

    note_list = list(notes or [])
    notes_text = " ".join(note_list)
    alternatives: list[str] = []
    alt_pattern = re.compile(r"Alt:\s*(\d{6,8})", re.IGNORECASE)
    for match in alt_pattern.finditer(notes_text):
        alt_number = normalize_course_number(match.group(1))
        if alt_number and alt_number not in alternatives:
            alternatives.append(alt_number)

    credits_range = None
    if credits_hint_raw:
        range_match = re.match(
            r"^(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)",
            credits_hint_raw.replace("≈", "").strip(),
        )
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            credits_range = {"min": low, "max": high}

    ref: dict[str, Any] = {
        "courseNumber": course_number,
        "titleHint": title_hint,
        "creditsHint": credits_hint,
        "facultyHint": None,
        "semestersOffered": [],
        "prerequisitesText": None,
        "corequisitesText": None,
        "noAdditionalCreditText": None,
        "footnoteMarkers": [],
        "pageNumbers": [],
        "sourceEvidence": evidence,
        "notes": note_list,
        "manualReviewRequired": bool(alternatives or credits_range),
        "confidence": "medium" if title_hint else "low",
        "offeringMetadataNote": (
            "Semester offering JSON reference only; not the full canonical catalog."
        ),
    }
    if credits_hint_raw and credits_range:
        note_list = list(ref["notes"])
        note_list.append(f"Credits range: {credits_hint_raw}")
        ref["notes"] = note_list
    if alternatives:
        note_list = list(ref["notes"])
        note_list.append(f"Alternatives: {', '.join(alternatives)}")
        ref["notes"] = note_list
    return _to_catalog_course_reference(ref)


def enrich_course_reference(ref: dict[str, Any], offering_index: dict[str, Any]) -> dict[str, Any]:
    number = ref.get("courseNumber")
    if not number:
        return ref

    offering = offering_index.get(number)
    if offering is None:
        return ref

    enriched = dict(ref)
    source_files = offering.get("sourceFiles") or []
    source_label = ",".join(Path(item).name for item in source_files)

    if offering.get("titleHebrew"):
        wiki_title = enriched.get("titleHint")
        json_title = offering["titleHebrew"]
        if wiki_title and wiki_title != json_title:
            notes = list(enriched.get("notes") or [])
            notes.append(f"Wiki title {wiki_title!r} differs from offering JSON {json_title!r}.")
            enriched["notes"] = notes
        if not wiki_title:
            enriched["titleHint"] = json_title

    if offering.get("credits") is not None:
        json_credits = float(offering["credits"])
        hint = enriched.get("creditsHint")
        if hint is not None and abs(float(hint) - json_credits) > 0.25:
            notes = list(enriched.get("notes") or [])
            notes.append(f"Wiki creditsHint {hint} differs from semester JSON {json_credits}; using JSON.")
            enriched["notes"] = notes
        enriched["creditsHint"] = json_credits

    if offering.get("faculty"):
        enriched["facultyHint"] = offering["faculty"]
    if offering.get("prerequisitesText"):
        enriched["prerequisitesText"] = offering["prerequisitesText"]
    if offering.get("corequisitesText"):
        enriched["corequisitesText"] = offering["corequisitesText"]
    if offering.get("noAdditionalCreditText"):
        enriched["noAdditionalCreditText"] = offering["noAdditionalCreditText"]
    if offering.get("semestersOffered"):
        enriched["semestersOffered"] = offering["semestersOffered"]

    evidence = list(enriched.get("sourceEvidence") or [])
    if source_label:
        for field_name in ("creditsHint", "facultyHint", "semestersOffered"):
            if enriched.get(field_name) is not None:
                evidence.append(f"{field_name}:courses_{source_label}")
    enriched["sourceEvidence"] = sorted(set(evidence))

    if enriched.get("titleHint"):
        enriched["confidence"] = "medium"
    return enriched


def _credit_bucket_groups(program_code: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for label, slug, requirement_type, min_credits in config["creditBuckets"]:
        groups.append(
            {
                "groupId": f"{program_code}:{slug}",
                "title": label,
                "requirementType": requirement_type,
                "minCredits": min_credits,
                "courseReferences": [],
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
                "pageNumbers": [],
                "notes": [],
                "manualReviewRequired": False,
                "confidence": "high",
            }
        )
    return groups


def _semester_matrix_groups(
    page: WikiPage,
    program_code: str,
    *,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    english = page.english_body
    for match in SEMESTER_HEADING_PATTERN.finditer(english):
        semester = int(match.group(1))
        start = match.end()
        next_heading = re.search(r"^#{2,3}\s+", english[start:], re.MULTILINE)
        section = english[start : start + next_heading.start()] if next_heading else english[start:]
        tables = parse_markdown_tables(section)
        course_refs: list[dict[str, Any]] = []
        for table in tables:
            for row in _table_course_rows(table, pages=pages):
                ref = build_course_reference(
                    row["code"] or "",
                    title_hint=row.get("name"),
                    credits_hint=parse_credits_value(row.get("credits")),
                    credits_hint_raw=row.get("credits"),
                    source_page=page.path,
                    notes=[row["notes"]] if row.get("notes") else [],
                )
                if ref is not None:
                    course_refs.append(ref)
        if not course_refs:
            continue
        groups.append(
            {
                "groupId": f"{program_code}:semester-{semester}-matrix",
                "title": f"Recommended mandatory semester {semester}",
                "requirementType": "core",
                "minCredits": None,
                "courseReferences": course_refs,
                "ruleExpression": {
                    "type": "semester_matrix",
                    "operator": "all_of",
                    "semester": semester,
                },
                "pageNumbers": [],
                "notes": [],
                "manualReviewRequired": True,
                "confidence": "medium",
            }
        )

    by_semester: dict[int, dict[str, Any]] = {}
    for group in groups:
        semester = int((group.get("ruleExpression") or {}).get("semester") or 0)
        existing = by_semester.get(semester)
        if existing is None:
            by_semester[semester] = group
            continue
        existing["courseReferences"] = _merge_unique_course_refs(
            existing.get("courseReferences") or [],
            group.get("courseReferences") or [],
        )
    return list(by_semester.values())


def _course_pool_group(
    *,
    program_code: str,
    group_suffix: str,
    title: str,
    course_refs: list[dict[str, Any]],
    rule_expression: dict[str, Any],
    min_credits: float | None = None,
    notes: list[str] | None = None,
    catalog_description: str | None = None,
) -> dict[str, Any]:
    group = {
        "groupId": f"{program_code}:{group_suffix}",
        "title": title,
        "requirementType": "elective",
        "minCredits": min_credits,
        "courseReferences": course_refs,
        "ruleExpression": rule_expression,
        "pageNumbers": [],
        "notes": notes or [],
        "manualReviewRequired": True,
        "confidence": "medium" if course_refs else "low",
    }
    if catalog_description:
        group["catalogDescription"] = catalog_description
    return group


def _merge_unique_course_refs(*reference_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for references in reference_lists:
        for reference in references:
            number = reference.get("courseNumber")
            if not number or str(number) in seen:
                continue
            seen.add(str(number))
            merged.append(reference)
    return merged


def _row_is_dne_starred(row: dict[str, str | None]) -> bool:
    notes = row.get("notes") or ""
    name = row.get("name") or ""
    return "*" in notes or "*" in name


def _dne_starred_course_refs(pages: dict[str, WikiPage]) -> list[dict[str, Any]]:
    dne = pages.get("track-data-information-engineering")
    if dne is None:
        return [
            ref
            for number in DNE_STARRED_COURSE_NUMBERS
            if (ref := build_course_reference(number, source_page=None)) is not None
        ]

    english = dne.english_body
    elective_start = english.find("## DNE Elective Course List")
    if elective_start < 0:
        return []

    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in parse_markdown_tables(english[elective_start:]):
        for row in _table_course_rows(table):
            if not _row_is_dne_starred(row):
                continue
            ref = build_course_reference(
                row["code"] or "",
                title_hint=row.get("name"),
                credits_hint=parse_credits_value(row.get("credits")),
                credits_hint_raw=row.get("credits"),
                source_page=dne.path,
            )
            if ref is None:
                continue
            number = str(ref.get("courseNumber") or "")
            if number in seen:
                continue
            seen.add(number)
            refs.append(ref)
    return refs


def _collect_course_numbers(text: str) -> list[str]:
    return collect_course_numbers_from_text(text)


def _focus_chain_section_end(
    section: str,
    start: int,
    *,
    other_chain_labels: tuple[str, ...],
    next_group_markers: tuple[str, ...],
) -> int:
    end_candidates = [
        section.find(other, start + 1)
        for other in other_chain_labels
        if section.find(other, start + 1) >= 0
    ]
    for marker in next_group_markers:
        marker_pos = section.find(marker, start + 1)
        if marker_pos >= 0:
            end_candidates.append(marker_pos)
    return min(end_candidates) if end_candidates else len(section)


def _table_course_refs(
    page: WikiPage,
    table: MarkdownTable,
    *,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in _table_course_rows(table, pages=pages):
        ref = build_course_reference(
            row["code"] or "",
            title_hint=row.get("name"),
            credits_hint=parse_credits_value(row.get("credits")),
            credits_hint_raw=row.get("credits"),
            source_page=page.path,
        )
        if ref is not None:
            refs.append(ref)
    return refs


def _dne_specialization_groups(pages: dict[str, WikiPage], program_code: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    cognition = pages.get("specialization-cognitive-science")
    if cognition is not None:
        refs: list[dict[str, Any]] = []
        for table in parse_markdown_tables(cognition.english_body):
            refs.extend(_table_course_refs(cognition, table))
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix="cognition-track:requirements",
                title="Cognitive science specialization requirements",
                course_refs=refs,
                rule_expression={"type": "track_requirement", "operator": "min_credits", "minCredits": 30},
                notes=["Specialization track; choose-N semantics preserved as advisory pool."],
            )
        )

    math_page = pages.get("specialization-math-analysis")
    if math_page is not None:
        refs = []
        for table in parse_markdown_tables(math_page.english_body):
            refs.extend(_table_course_refs(math_page, table))
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix="math-analytics-track:requirements",
                title="Mathematical analysis specialization requirements",
                course_refs=refs,
                rule_expression={"type": "track_requirement", "operator": "min_credits", "minCredits": 26},
            )
        )

    return groups


FACULTY_PREFIX_RULE: dict[str, Any] = {
    "type": "course_pool",
    "operator": "min_credits",
    "allowedPrefixes": ["0094", "0095", "0096", "0097"],
}

FACULTY_ADDITIONAL_RULE: dict[str, Any] = {
    **FACULTY_PREFIX_RULE,
    "alwaysIncludeCourseNumbers": ["2160035"],
}

ENRICHMENT_POOL_RULE: dict[str, Any] = {
    "type": "course_pool",
    "operator": "min_credits",
    "allowedPrefixes": ["039405"],
}

PHYSICAL_EDUCATION_POOL_RULE: dict[str, Any] = {
    "type": "course_pool",
    "operator": "min_credits",
    "allowedPrefixes": ["039408", "039409"],
}

FREE_ELECTIVE_POOL_RULE: dict[str, Any] = {
    "type": "course_pool",
    "operator": "min_credits",
}

GENERAL_TECHNION_ENRICHMENT_DESCRIPTION = (
    "University enrichment (CHE / קורסי העשרה): at least 6 credits from Technion-wide "
    "enrichment courses approved by the Center for Humanistic Education."
)
GENERAL_TECHNION_FREE_ELECTIVE_DESCRIPTION = (
    "Free electives: Technion course credits not already applied to faculty or mandatory "
    "requirements (typically 4 credits in DDS tracks)."
)
GENERAL_TECHNION_PHYSICAL_EDUCATION_DESCRIPTION = (
    "Physical education (חינוך גופני): 2 credits required; maximum 1.5 credits per semester."
)

TECHNION_WIDE_ENRICHMENT_CREDITS = 6.0
TECHNION_WIDE_PHYSICAL_EDUCATION_CREDITS = 2.0
DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL = 12.0


def technion_wide_elective_credit_split(
    technion_wide_total: float = DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL,
) -> tuple[float, float, float]:
    """Split Technion-wide elective total into enrichment / free / physical-education buckets."""
    enrichment = TECHNION_WIDE_ENRICHMENT_CREDITS
    physical = TECHNION_WIDE_PHYSICAL_EDUCATION_CREDITS
    free = max(0.0, round(float(technion_wide_total) - enrichment - physical, 2))
    return enrichment, free, physical


def _general_technion_credit_bucket_groups(
    program_code: str,
    *,
    technion_wide_total: float = DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL,
) -> list[dict[str, Any]]:
    """Hard credit buckets for enrichment / free-elective / physical-education (linked from pools)."""
    enrichment, free, physical = technion_wide_elective_credit_split(technion_wide_total)
    return _credit_bucket_groups(
        program_code,
        {
            "creditBuckets": [
                ("University enrichment", "enrichment", "enrichment", enrichment),
                ("Free electives", "free-elective", "elective", free),
                ("Physical education", "physical-education", "enrichment", physical),
            ],
        },
    )


def _general_technion_elective_groups(
    program_code: str,
    *,
    technion_wide_total: float = DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL,
) -> list[dict[str, Any]]:
    """Advisory pools linked to enrichment / free-elective / physical-education credit buckets."""
    enrichment, free, physical = technion_wide_elective_credit_split(technion_wide_total)
    return [
        _course_pool_group(
            program_code=program_code,
            group_suffix="enrichment-pool",
            title="University enrichment pool",
            course_refs=[],
            min_credits=enrichment,
            rule_expression=ENRICHMENT_POOL_RULE,
            catalog_description=GENERAL_TECHNION_ENRICHMENT_DESCRIPTION,
            notes=["Eligible courses use catalog prefix 039405 (CHE enrichment)."],
        ),
        _course_pool_group(
            program_code=program_code,
            group_suffix="free-elective-pool",
            title="Free electives pool",
            course_refs=[],
            min_credits=free,
            rule_expression=FREE_ELECTIVE_POOL_RULE,
            catalog_description=GENERAL_TECHNION_FREE_ELECTIVE_DESCRIPTION,
            notes=["No fixed course list; progress uses remaining eligible transcript credits."],
        ),
        _course_pool_group(
            program_code=program_code,
            group_suffix="physical-education-pool",
            title="Physical education pool",
            course_refs=[],
            min_credits=physical,
            rule_expression=PHYSICAL_EDUCATION_POOL_RULE,
            catalog_description=GENERAL_TECHNION_PHYSICAL_EDUCATION_DESCRIPTION,
            notes=["Eligible courses use catalog prefixes 039408 or 039409."],
        ),
    ]


def _dne_elective_groups(page: WikiPage, program_code: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    heading = config.get("electivePoolHeading")
    if heading:
        pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)
        match = pattern.search(page.english_body)
        if match:
            tables = parse_markdown_tables(page.english_body[match.end() :])
            refs: list[dict[str, Any]] = []
            for table in tables:
                refs.extend(_table_course_refs(page, table))
            if refs:
                groups.append(
                    _course_pool_group(
                        program_code=program_code,
                        group_suffix="dne-elective-list-pool",
                        title="DNE elective course list",
                        course_refs=refs,
                        rule_expression={
                            "type": "course_pool",
                            "operator": "choose_n",
                            "chooseCount": 1,
                        },
                        catalog_description=(
                            "Complete DNE elective credits from this catalog list; "
                            "must include at least 2 courses marked * (data-intensive projects)."
                        ),
                        notes=["Must include at least 2 courses marked * in the source catalog."],
                    )
                )
            groups.append(
                _course_pool_group(
                    program_code=program_code,
                    group_suffix=config["electivePoolGroupId"],
                    title="Data science elective pool",
                    course_refs=refs,
                    min_credits=24.5,
                    rule_expression={"type": "course_pool", "operator": "min_credits"},
                    notes=["Must include at least 2 courses marked * in the source catalog."],
                )
            )
            groups.append(
                _course_pool_group(
                    program_code=program_code,
                    group_suffix=config["facultyPoolGroupId"],
                    title="Faculty elective pool",
                    course_refs=[],
                    min_credits=10.5,
                    rule_expression={
                        **FACULTY_PREFIX_RULE,
                        "includesPoolSuffix": "elective-ds-pool",
                    },
                    notes=["Any DNE elective or faculty course with prefix 094/095/096/097."],
                )
            )
    return groups


def _iem_elective_groups(page: WikiPage, program_code: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    english = page.english_body

    stats_table = find_table_with_header(english[english.find("Group 1") :], "Code")
    if stats_table is not None:
        stats_refs = _table_course_refs(page, stats_table)
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix="ie-statistics-elective-chain",
                title="IE statistics elective chain",
                course_refs=stats_refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": 1,
                    "chain": "statistics",
                },
                notes=["Choose-N chain; not flattened mandatory list."],
                catalog_description=IE_STATISTICS_CATALOG_DESCRIPTION,
            )
        )

    behavior_table = find_table_with_header(english[english.find("Group 2") :], "Code")
    if behavior_table is not None:
        behavior_refs = _table_course_refs(page, behavior_table)
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix="ie-behavior-science-chain",
                title="IE behavioral sciences chain",
                course_refs=behavior_refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": 1,
                    "chain": "behavior_science",
                },
                catalog_description=IE_BEHAVIOR_SCIENCE_CATALOG_DESCRIPTION,
            )
        )

    focus_section = english[english.find("Group 3") :] if "Group 3" in english else ""
    chain_map = {
        "Chain A": "ie-focus-chain-game-theory",
        "Chain B": "ie-focus-chain-advanced-industry",
        "Chain C": "ie-focus-chain-operations-research",
    }
    for label, suffix in chain_map.items():
        start = focus_section.find(label)
        if start < 0:
            continue
        end = _focus_chain_section_end(
            focus_section,
            start,
            other_chain_labels=tuple(other for other in chain_map if other != label),
            next_group_markers=("Group 4", "### Group 4"),
        )
        chain_text = focus_section[start:end]
        refs = [
            ref
            for number in _collect_course_numbers(chain_text)
            if (ref := build_course_reference(number, source_page=page.path)) is not None
        ]
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=suffix,
                title=f"IE focus chain ({label})",
                course_refs=refs,
                rule_expression={"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
                catalog_description=_iem_focus_chain_description(label),
            )
        )

    additional_section = english[english.find("Group 4") :] if "Group 4" in english else ""
    additional_numbers = _collect_course_numbers(additional_section)
    additional_refs = [
        ref
        for number in additional_numbers
        if (ref := build_course_reference(number, source_page=page.path)) is not None
    ]
    groups.append(
        _course_pool_group(
            program_code=program_code,
            group_suffix="ie-additional-faculty-electives",
            title="IE additional faculty electives",
            course_refs=additional_refs,
            rule_expression=FACULTY_ADDITIONAL_RULE,
            notes=["Remaining faculty electives: any course with prefix 094–097 plus 2160035."],
        )
    )
    return groups


def _iem_focus_chain_description(label: str) -> str:
    descriptions = {
        "Chain A": (
            "Group 3 — Game theory & economic behavior focus chain. Complete all 3 parts: "
            "Part 1: one of 0960226, 0960570, 0960578, 0970317. "
            "Part 2: one of 0960606, 0960617, 0960690. "
            "Part 3: one more from Part 1 or 2, or 0960211."
        ),
        "Chain B": (
            "Group 3 — Advanced industry focus chain. Complete all 3 parts: "
            "Part 1 (required): 0960411 Computational learning 1. "
            "Part 2: one of 0940222, 0950111, 0960210, 0970247. "
            "Part 3: one from Part 2 list or 0960208, 0960266, 0960625, 0970139, 0960135, 0970244."
        ),
        "Chain C": (
            "Group 3 — Operations research focus chain. Complete all 3 parts: "
            "Part 1 (required): 0960327 Nonlinear models in operations research. "
            "Part 2 (required): 0960570 Game theory and economic behavior (0980413 may substitute). "
            "Part 3: one of 0960311, 0960335."
        ),
    }
    return descriptions.get(label, "Complete one 3-course focus chain from the catalog.")


def _is_focus_chain_description(label: str) -> str:
    descriptions = {
        "Chain A": (
            "Part 1 (required): 0960327 Nonlinear models in operations research. "
            "Part 2 (required): 0960324 Service systems engineering (0980413 may substitute). "
            "Part 3: one of 0960311, 0960335, 0960351, 0970135, 0970280, 0970325, 0970334."
        ),
        "Chain B": (
            "Part 1 (required): 0970209 Computational learning 2. "
            "Part 2: one of 0960212, 0960327, 0970414. "
            "Part 3: one course marked * from the DNE elective list."
        ),
        "Chain C": (
            "Part 1: one of 0960226, 0960578, 0970317. "
            "Part 2: one of 0960606, 0960617, 0960690. "
            "Part 3: one more from Part 1 or Part 2."
        ),
    }
    return descriptions.get(label, "Complete one 3-course focus chain from the catalog.")


def _is_elective_groups(
    page: WikiPage,
    program_code: str,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    english = page.english_body
    wiki_pages = pages or {}

    behavior_table = find_table_with_header(english[english.find("Group 1") :], "Code")
    if behavior_table is not None:
        behavior_refs = _table_course_refs(page, behavior_table)
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix="is-behavior-science-chain",
                title="IS behavioral sciences chain",
                course_refs=behavior_refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": 1,
                    "chain": "behavior_science",
                },
                catalog_description=IS_BEHAVIOR_SCIENCE_CATALOG_DESCRIPTION,
            )
        )

    focus_section = english[english.find("Group 2") :] if "Group 2" in english else ""
    chain_map = {
        "Chain A": "is-focus-chain-performance",
        "Chain B": "is-focus-chain-ml",
        "Chain C": "is-focus-chain-game-theory",
    }
    dne_starred_refs = _dne_starred_course_refs(wiki_pages)
    for label, suffix in chain_map.items():
        start = focus_section.find(label)
        if start < 0:
            continue
        end = _focus_chain_section_end(
            focus_section,
            start,
            other_chain_labels=tuple(other for other in chain_map if other != label),
            next_group_markers=("Group 3", "### Group 3"),
        )
        chain_text = focus_section[start:end]
        refs = [
            ref
            for number in _collect_course_numbers(chain_text)
            if (ref := build_course_reference(number, source_page=page.path)) is not None
        ]
        if suffix == "is-focus-chain-ml":
            refs = _merge_unique_course_refs(refs, dne_starred_refs)
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=suffix,
                title=f"IS focus chain ({label})",
                course_refs=refs,
                rule_expression={"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
                catalog_description=_is_focus_chain_description(label),
            )
        )

    additional_section = english[english.find("Group 3") :] if "Group 3" in english else ""
    additional_refs = [
        ref
        for number in _collect_course_numbers(additional_section)
        if (ref := build_course_reference(number, source_page=page.path)) is not None
    ]
    groups.append(
        _course_pool_group(
            program_code=program_code,
            group_suffix="is-additional-faculty-electives",
            title="IS additional faculty electives",
            course_refs=additional_refs,
            rule_expression=FACULTY_ADDITIONAL_RULE,
            notes=[
                "Remaining faculty electives: prefix 094–097 plus 2160035; see IE track for examples.",
            ],
        )
    )
    return groups


def build_program(page: WikiPage, config: dict[str, Any], pages: dict[str, WikiPage]) -> dict[str, Any]:
    program_code = config["programCode"]
    name_he = page.title_he or extract_field(page.english_body, "Hebrew name") or page.title
    total_credits = parse_credits_value(extract_field(page.english_body, "Total credits required") or "155")

    requirement_groups = _credit_bucket_groups(program_code, config)
    requirement_groups.extend(_semester_matrix_groups(page, program_code))

    if page.slug == "track-data-information-engineering":
        requirement_groups.extend(_dne_elective_groups(page, program_code, config))
        requirement_groups.extend(_dne_specialization_groups(pages, program_code))
    elif page.slug == "track-industrial-engineering-management":
        requirement_groups.extend(_iem_elective_groups(page, program_code))
    elif page.slug == "track-information-systems-engineering":
        requirement_groups.extend(_is_elective_groups(page, program_code, pages))

    requirement_groups.extend(_general_technion_elective_groups(program_code))

    return {
        "institutionId": INSTITUTION_ID,
        "programCode": program_code,
        "name": name_he,
        "nameEn": config["nameEn"],
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "totalCredits": total_credits or 155.0,
        "paths": [],
        "requirementGroups": requirement_groups,
        "pageNumbers": [],
        "metadata": {"faculty": "dds", "facultyId": "faculty-dds", "wikiPage": page.slug, "programKind": "bsc_track"},
        "manualReviewRequired": True,
        "confidence": "medium",
    }


def enrich_programs(programs: list[dict[str, Any]], offering_index: dict[str, Any]) -> None:
    for program in programs:
        for group in program.get("requirementGroups", []):
            refs = group.get("courseReferences") or []
            group["courseReferences"] = [
                enrich_course_reference(ref, offering_index) for ref in refs
            ]


def count_export_stats(document: dict[str, Any]) -> dict[str, int]:
    programs = document.get("programs") or []
    requirement_groups = sum(len(program.get("requirementGroups") or []) for program in programs)
    course_refs = 0
    missing_titles = 0
    manual_review = 0
    executable = 0
    non_executable = 0

    if document.get("source", {}).get("manualReviewRequired"):
        manual_review += 1

    for program in programs:
        if program.get("manualReviewRequired"):
            manual_review += 1
        for group in program.get("requirementGroups") or []:
            if group.get("manualReviewRequired"):
                manual_review += 1
            rule_type = (group.get("ruleExpression") or {}).get("type")
            if rule_type == "credit_bucket":
                executable += 1
            else:
                non_executable += 1
            for ref in group.get("courseReferences") or []:
                course_refs += 1
                if ref.get("manualReviewRequired"):
                    manual_review += 1
                if not ref.get("titleHint"):
                    missing_titles += 1

    return {
        "programs": len(programs),
        "requirementGroups": requirement_groups,
        "courseReferences": course_refs,
        "missingTitleHints": missing_titles,
        "manualReviewRequiredItems": manual_review,
        "executableRuleGroups": executable,
        "nonExecutableRuleGroups": non_executable,
    }


def build_readiness_check(
    document: dict[str, Any],
    *,
    expected_program_codes: frozenset[str] | None = None,
) -> dict[str, Any]:
    counts = count_export_stats(document)
    warnings: list[str] = []
    blocking_staging: list[str] = []
    blocking_production = [
        "Production promotion gate must pass staging quality checks.",
    ]

    expected_codes = expected_program_codes or frozenset(
        {"009216-1-000", "009009-1-000", "009118-1-000"}
    )
    exported_codes = {program["programCode"] for program in document.get("programs") or []}
    missing_codes = sorted(expected_codes - exported_codes)
    if missing_codes:
        blocking_staging.append(f"Missing program codes: {', '.join(missing_codes)}")

    if counts["missingTitleHints"]:
        warnings.append(f"{counts['missingTitleHints']} course references still lack titleHint.")

    can_import = not blocking_staging
    return {
        "canImportToStaging": can_import,
        "canPromoteToProduction": False,
        "blockingIssuesForStaging": blocking_staging,
        "blockingIssuesForProduction": blocking_production,
        "warnings": warnings,
        "reviewStatus": "ready-for-staging-with-review-flags",
        "phase8Recommendation": (
            "Safe to import to staging with review flags preserved."
            if can_import
            else "Resolve staging blockers before import."
        ),
        "productionPromotionRecommendation": "Do not promote to production until human signoff.",
        "counts": counts,
    }


def export_dds_vault_catalog(
    *,
    vault_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    faculty = "dds"
    root = wiki_root(vault_path or catalog_vault_root())
    pages = load_pages_by_slug(root)

    offering_index = {
        number: record.to_dict()
        for number, record in build_course_index(course_json_paths or default_course_json_paths()).items()
    }

    programs = [
        build_program(pages[slug], config, pages)
        for slug, config in DDS_TRACK_SLUGS.items()
        if slug in pages
    ]
    enrich_programs(programs, offering_index)

    path_catalog = build_wiki_path_catalog(
        wiki_path=root,
        institution_id=INSTITUTION_ID,
        faculty_id="faculty-dds",
        track_program_codes={slug: config["programCode"] for slug, config in DDS_TRACK_SLUGS.items()},
        catalog_year=CATALOG_YEAR,
        catalog_version=CATALOG_VERSION,
    )

    wiki_source = _relative_vault_path(root)
    export_report = {
        "exporter": "vault-export",
        "faculty": faculty,
        "wikiRoot": wiki_source,
        "trackPagesExported": [slug for slug in DDS_TRACK_SLUGS if slug in pages],
        "courseJsonSources": [
            _relative_vault_path(path) for path in (course_json_paths or default_course_json_paths())
        ],
        "exportedAt": _utc_now_iso(),
    }

    unresolved: list[str] = []
    counts = count_export_stats({"programs": programs, "source": {"manualReviewRequired": True}})
    if counts["missingTitleHints"]:
        unresolved.append(f"{counts['missingTitleHints']} course references lack titleHint.")

    document: dict[str, Any] = {
        "source": {
            "institutionId": INSTITUTION_ID,
            "facultyId": faculty,
            "sourceName": "technion-dds-catalog",
            "sourceType": "dds_catalog_curated_reviewed",
            "exportMode": "specialized",
            "expectedProgramCodes": sorted(
                config["programCode"] for config in DDS_TRACK_SLUGS.values()
            ),
            "catalogYear": CATALOG_YEAR,
            "catalogVersion": CATALOG_VERSION,
            "sourceFile": wiki_source,
            "pageReferences": [],
            "manualReviewRequired": True,
            "confidence": "medium",
            "notes": ["Exported deterministically from catalog_valut wiki pages."],
        },
        "programs": programs,
        "faculties": path_catalog["faculties"],
        "pathOptions": path_catalog["pathOptions"],
        "parserReport": {
            **export_report,
            "pathOptionsExported": len(path_catalog["pathOptions"]),
            "facultiesExported": len(path_catalog["faculties"]),
        },
        "curationMetadata": {
            "curatedBy": "vault-export",
            "curatedAt": _utc_now_iso(),
            "sourceDraftPath": wiki_source,
            "sourceMarkdownPath": wiki_source,
            "courseJsonSources": export_report["courseJsonSources"],
            "curationStatus": "ready-for-staging-with-review-flags",
            "knownLimitations": [
                "Focus-chain choose-N semantics are encoded as non-executable pools.",
                "Science placeholder rows without course codes are omitted.",
            ],
            "countsBefore": {},
            "countsAfter": counts,
            "unresolvedIssues": unresolved,
        },
        "curationReport": {"warnings": unresolved},
        "signoffReview": {
            "reviewedBy": "vault-export",
            "reviewedAt": _utc_now_iso(),
            "reviewStatus": "ready-for-staging-with-review-flags",
            "sourceFilesReviewed": [wiki_source],
            "checksPerformed": [
                "program_codes_present",
                "credit_buckets_present",
                "semester_matrices_parsed",
                "course_numbers_normalized",
                "elective_chain_contract",
            ],
            "verifiedItems": [
                f"Exported {len(programs)} DDS programs from wiki track pages.",
            ],
            "unresolvedItems": unresolved,
            "phase8Recommendation": "Safe to import to staging with review flags preserved.",
            "productionPromotionRecommendation": (
                "Vault sign-off is applied automatically at export time."
            ),
        },
    }

    apply_vault_signoff_to_catalog(
        document,
        vault_path=vault_path or catalog_vault_root(),
        course_json_paths=course_json_paths,
    )
    readiness = build_readiness_after_vault_signoff(document)
    ReviewedCuratedCatalogDocument.model_validate(document)
    Phase8ReadinessCheck.model_validate(readiness)
    return document, readiness


def export_vault_catalog(
    *,
    vault_path: Path | None = None,
    faculty: str = "dds",
    course_json_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible facade — routes through the multi-faculty export registry."""
    from app.vault.vault_export_registry import export_vault_catalog as registry_export

    return registry_export(
        vault_path=vault_path,
        faculty=faculty,
        course_json_paths=course_json_paths,
    )


def write_vault_catalog_export(
    *,
    vault_path: Path | None = None,
    faculty: str = "dds",
    output_path: Path | None = None,
    readiness_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    document, readiness = export_vault_catalog(
        vault_path=vault_path,
        faculty=faculty,
        course_json_paths=course_json_paths,
    )

    catalog_path = output_path or default_catalog_reviewed_path(faculty)
    readiness_file = readiness_path or default_readiness_path(faculty)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    readiness_file.parent.mkdir(parents=True, exist_ok=True)

    catalog_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    readiness_file.write_text(
        json.dumps(readiness, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return catalog_path, readiness_file, document, readiness
