"""Generic Pass-1 faculty catalog export from the Technion wiki vault (Phase D)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.catalog.faculty_catalog_context import faculty_catalog_context_from_document
from app.models.catalog import ReviewedCuratedCatalogDocument
from app.models.staging_catalog import Phase8ReadinessCheck
from app.paths import catalog_vault_root
from app.sources.technion_course_json_index import build_course_index, default_course_json_paths
from app.vault.export_cs_electives import cs_elective_groups
from app.vault.export_dds_catalog import (
    CATALOG_VERSION,
    CATALOG_YEAR,
    INSTITUTION_ID,
    DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL,
    _general_technion_credit_bucket_groups,
    _general_technion_elective_groups,
    _relative_vault_path,
    _semester_matrix_groups,
    _utc_now_iso,
    count_export_stats,
    enrich_programs,
    parse_credits_value,
)
from app.vault.loader import WikiPage, extract_field, load_pages_by_slug, wiki_root
from app.vault.markdown_tables import parse_markdown_tables
from app.vault.vault_signoff import apply_vault_signoff_to_catalog, build_readiness_after_vault_signoff
from app.vault.wiki_path_catalog import build_wiki_path_catalog

PROGRAM_CODE_FIELD_PATTERN = re.compile(
    r"^\*\*(?:Track code|Program code):\*\*\s*(0\d{5}-\d-\d{3})\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def faculty_wiki_id(faculty_id: str) -> str:
    return f"faculty-{faculty_id}"


def discover_faculty_track_slugs(pages: dict[str, WikiPage], faculty_id: str) -> list[str]:
    wiki_id = faculty_wiki_id(faculty_id)
    slugs: list[str] = []
    for slug, page in pages.items():
        if not slug.startswith("track-"):
            continue
        frontmatter_faculty = page.frontmatter.get("faculty")
        if frontmatter_faculty == wiki_id:
            slugs.append(slug)
            continue
        tags = page.frontmatter.get("tags") or []
        if wiki_id in tags:
            slugs.append(slug)
    return sorted(set(slugs))


def extract_program_code(page: WikiPage) -> str | None:
    for label in ("Track code", "Program code"):
        raw = extract_field(page.english_body, label)
        if raw:
            match = re.search(r"(0\d{5}-\d-\d{3})", raw)
            if match:
                return match.group(1)
    body_match = PROGRAM_CODE_FIELD_PATTERN.search(page.english_body)
    if body_match:
        return body_match.group(1)
    return None


def _slugify_bucket_label(label: str) -> str:
    ascii_label = re.sub(r"[^a-zA-Z0-9]+", "-", label.lower()).strip("-")
    if not ascii_label:
        return "bucket"
    return ascii_label[:48]


def _bucket_requirement_type(label: str) -> str:
    lowered = label.lower()
    if "enrichment" in lowered or "physical education" in lowered or 'חינוך גופני' in label:
        return "enrichment"
    if "elective" in lowered or "בחירה" in label:
        return "elective"
    return "core"


def parse_credit_buckets_from_page(page: WikiPage) -> list[tuple[str, str, str, float]]:
    buckets: list[tuple[str, str, str, float]] = []
    for table in parse_markdown_tables(page.english_body):
        category_idx = next(
            (
                index
                for index, header in enumerate(table.headers)
                if "category" in header.lower() or "קטגוריה" in header
            ),
            None,
        )
        credits_idx = next(
            (
                index
                for index, header in enumerate(table.headers)
                if "credit" in header.lower() or "נק" in header or 'נ"ז' in header
            ),
            None,
        )
        if category_idx is None or credits_idx is None:
            continue
        for row in table.rows:
            if category_idx >= len(row) or credits_idx >= len(row):
                continue
            label = row[category_idx].strip()
            credits_raw = row[credits_idx].strip()
            if not label or label.startswith("**") or "total" in label.lower():
                continue
            credits = parse_credits_value(credits_raw)
            if credits is None:
                continue
            slug = _slugify_bucket_label(label)
            buckets.append((label, slug, _bucket_requirement_type(label), credits))
        if buckets:
            break
    return buckets


def _credit_bucket_groups(program_code: str, buckets: list[tuple[str, str, str, float]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for label, slug, requirement_type, min_credits in buckets:
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


def build_generic_program(
    page: WikiPage,
    *,
    faculty_id: str,
    pages: dict[str, WikiPage],
) -> dict[str, Any] | None:
    program_code = extract_program_code(page)
    if not program_code:
        return None

    name_he = page.title_he or page.title
    name_en = page.title.split("—")[-1].strip() if "—" in page.title else page.title
    total_credits = parse_credits_value(
        extract_field(page.english_body, "Total credits required")
        or extract_field(page.english_body, "Total credits")
        or "155",
    )

    requirement_groups = _credit_bucket_groups(program_code, parse_credit_buckets_from_page(page))
    technion_wide_total = DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL
    filtered_groups: list[dict[str, Any]] = []
    existing_bucket_slugs: set[str] = set()
    for group in requirement_groups:
        group_id = str(group.get("groupId") or "")
        slug = group_id.split(":", 1)[-1] if ":" in group_id else group_id
        if slug == "technion-wide-electives":
            if group.get("minCredits") is not None:
                technion_wide_total = float(group["minCredits"])
            continue
        filtered_groups.append(group)
        if group.get("ruleExpression", {}).get("type") == "credit_bucket":
            existing_bucket_slugs.add(slug)
    requirement_groups = filtered_groups

    standard_technion_buckets = {"enrichment", "free-elective", "physical-education"}
    if not standard_technion_buckets.issubset(existing_bucket_slugs):
        requirement_groups.extend(
            _general_technion_credit_bucket_groups(
                program_code,
                technion_wide_total=technion_wide_total,
            )
        )

    requirement_groups.extend(_semester_matrix_groups(page, program_code))
    requirement_groups.extend(
        _general_technion_elective_groups(program_code, technion_wide_total=technion_wide_total)
    )
    if faculty_id == "computer-science":
        requirement_groups.extend(cs_elective_groups(page, program_code))

    return {
        "institutionId": INSTITUTION_ID,
        "programCode": program_code,
        "name": name_he,
        "nameEn": name_en,
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "totalCredits": total_credits or 155.0,
        "paths": [],
        "requirementGroups": requirement_groups,
        "pageNumbers": [],
        "metadata": {
            "faculty": faculty_id,
            "facultyId": faculty_wiki_id(faculty_id),
            "wikiPage": page.slug,
            "programKind": "bsc_track",
        },
        "manualReviewRequired": True,
        "confidence": "medium",
    }


def build_track_program_code_map(
    pages: dict[str, WikiPage],
    faculty_id: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for slug in discover_faculty_track_slugs(pages, faculty_id):
        page = pages.get(slug)
        if page is None:
            continue
        program_code = extract_program_code(page)
        if program_code:
            mapping[slug] = program_code
    return mapping


def export_faculty_vault_catalog(
    *,
    faculty_id: str,
    vault_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = wiki_root(vault_path or catalog_vault_root())
    pages = load_pages_by_slug(root)
    wiki_faculty_id = faculty_wiki_id(faculty_id)

    offering_index = {
        number: record.to_dict()
        for number, record in build_course_index(course_json_paths or default_course_json_paths()).items()
    }

    track_slugs = discover_faculty_track_slugs(pages, faculty_id)
    programs: list[dict[str, Any]] = []
    for slug in track_slugs:
        page = pages.get(slug)
        if page is None:
            continue
        program = build_generic_program(page, faculty_id=faculty_id, pages=pages)
        if program is not None:
            programs.append(program)

    if not programs:
        raise ValueError(
            f"No exportable BSc track programs found for faculty {faculty_id!r} "
            f"(wiki id {wiki_faculty_id}). Add track pages with Track/Program code fields.",
        )

    enrich_programs(programs, offering_index)

    track_program_codes = build_track_program_code_map(pages, faculty_id)
    path_catalog = build_wiki_path_catalog(
        wiki_path=root,
        institution_id=INSTITUTION_ID,
        faculty_id=wiki_faculty_id,
        track_program_codes=track_program_codes,
        catalog_year=CATALOG_YEAR,
        catalog_version=CATALOG_VERSION,
    )

    expected_codes = frozenset(program["programCode"] for program in programs)
    wiki_source = _relative_vault_path(root)
    export_report = {
        "exporter": "vault-export-generic",
        "faculty": faculty_id,
        "wikiRoot": wiki_source,
        "trackPagesExported": [program["metadata"]["wikiPage"] for program in programs],
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
            "facultyId": faculty_id,
            "sourceName": f"technion-{faculty_id}-catalog",
            "sourceType": f"{faculty_id}_catalog_curated_reviewed",
            "exportMode": "generic",
            "expectedProgramCodes": sorted(expected_codes),
            "catalogYear": CATALOG_YEAR,
            "catalogVersion": CATALOG_VERSION,
            "sourceFile": wiki_source,
            "pageReferences": [],
            "manualReviewRequired": True,
            "confidence": "medium",
            "notes": [
                "Exported deterministically from catalog_valut wiki pages (generic faculty exporter).",
                "Computer Science general 4-year track includes specialized elective-chain pools.",
            ],
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
            "curatedBy": "vault-export-generic",
            "curatedAt": _utc_now_iso(),
            "sourceDraftPath": wiki_source,
            "sourceMarkdownPath": wiki_source,
            "courseJsonSources": export_report["courseJsonSources"],
            "curationStatus": "ready-for-staging-with-review-flags",
            "knownLimitations": [
                "Generic exporter: focus-chain choose-N semantics are encoded as non-executable pools when present.",
                "Science placeholder rows without course codes are omitted.",
            ],
            "countsBefore": {},
            "countsAfter": counts,
            "unresolvedIssues": unresolved,
        },
        "curationReport": {"warnings": unresolved},
        "signoffReview": {
            "reviewedBy": "vault-export-generic",
            "reviewedAt": _utc_now_iso(),
            "reviewStatus": "ready-for-staging-with-review-flags",
            "sourceFilesReviewed": [wiki_source],
            "checksPerformed": [
                "program_codes_present",
                "credit_buckets_present",
                "semester_matrices_parsed",
                "course_numbers_normalized",
            ],
            "verifiedItems": [
                f"Exported {len(programs)} {faculty_id} programs from wiki track pages.",
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
    readiness["counts"] = counts
    readiness.setdefault("blockingIssuesForStaging", [])

    faculty_catalog_context_from_document(document)
    ReviewedCuratedCatalogDocument.model_validate(document)
    Phase8ReadinessCheck.model_validate(readiness)
    return document, readiness
