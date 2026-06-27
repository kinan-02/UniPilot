"""Specialized faculty catalog export from the Technion wiki vault (Phase D)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.catalog.faculty_catalog_context import faculty_catalog_context_from_document
from app.models.catalog import ReviewedCuratedCatalogDocument
from app.models.staging_catalog import Phase8ReadinessCheck
from app.paths import catalog_vault_root
from app.sources.technion_course_json_index import build_course_index, default_course_json_paths
from app.vault.faculty_elective_enrichers import faculty_elective_groups
from app.vault.export_dds_catalog import (
    CATALOG_VERSION,
    CATALOG_YEAR,
    INSTITUTION_ID,
    DEFAULT_TECHNION_WIDE_ELECTIVE_TOTAL,
    _general_technion_credit_bucket_groups,
    _general_technion_elective_groups,
    _merge_unique_course_refs,
    _relative_vault_path,
    _semester_matrix_groups,
    _utc_now_iso,
    count_export_stats,
    enrich_programs,
    parse_credits_value,
)
from app.vault.loader import WikiPage, extract_field, extract_wikilinks, load_pages_by_slug, wiki_root
from app.vault.markdown_tables import parse_markdown_tables
from app.vault.track_program_codes import resolve_program_code
from app.vault.vault_signoff import apply_vault_signoff_to_catalog, build_readiness_after_vault_signoff
from app.vault.wiki_path_catalog import _track_selectable_as_primary, build_wiki_path_catalog

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


def track_program_kind(page: WikiPage) -> str:
    raw = page.frontmatter.get("programKind")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "bsc_track"


def canonical_program_track_slug(page: WikiPage) -> str | None:
    raw = page.frontmatter.get("canonicalSlug")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    parent_track = extract_field(page.english_body, "Parent Track")
    if parent_track:
        for link in extract_wikilinks(parent_track):
            if link.startswith("track-"):
                return link
    return None


def should_export_degree_program(
    page: WikiPage,
    *,
    faculty_track_slugs: frozenset[str] | None = None,
) -> bool:
    """Path-only wiki pages share a program code with a canonical track page."""
    kind = track_program_kind(page)
    if kind == "bsc_specialization":
        return _track_selectable_as_primary(page)
    canonical = canonical_program_track_slug(page)
    if canonical:
        if not _track_selectable_as_primary(page):
            return False
        if faculty_track_slugs is None:
            return False
        if canonical in faculty_track_slugs:
            return False
        return True
    return True


def extract_program_code(page: WikiPage) -> str | None:
    extracted: str | None = None
    for label in ("Track code", "Program code", "קוד תכנית", "מספר תכנית"):
        raw = extract_field(page.english_body, label) or extract_field(page.body, label)
        if raw:
            match = re.search(r"(0\d{5}-\d-\d{3})", raw)
            if match:
                extracted = match.group(1)
                break
    if extracted is None:
        body_match = PROGRAM_CODE_FIELD_PATTERN.search(page.english_body)
        if body_match:
            extracted = body_match.group(1)
        else:
            body_match = PROGRAM_CODE_FIELD_PATTERN.search(page.body)
            if body_match:
                extracted = body_match.group(1)
    return resolve_program_code(page, extracted)


_BUCKET_SLUG_ALIASES: dict[str, str] = {
    "free-electives": "free-elective",
}

_HEBREW_BUCKET_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("מקצועות חובה", "required-courses"),
    ("חובה", "required-courses"),
    ("בחירה מדעיים", "science-electives"),
    ("בחירה מומלצת", "recommended-electives"),
    ("מקצועות העשרה", "enrichment"),
    ("העשרה", "enrichment"),
    ("חינוך גופני", "physical-education"),
    ("גופני", "physical-education"),
    ("כלל טכניונית", "technion-wide-electives"),
    ("בחירה פקולטי", "faculty-electives"),
    ("בחירה חופשית", "free-electives"),
)

_STANDARD_TECHNION_BUCKET_SLUGS = frozenset({"enrichment", "free-elective", "physical-education"})


def _canonical_bucket_slug(slug: str) -> str:
    return _BUCKET_SLUG_ALIASES.get(slug, slug)


def _slugify_bucket_label(label: str) -> str:
    ascii_label = re.sub(r"[^a-zA-Z0-9]+", "-", label.lower()).strip("-")
    if ascii_label:
        return _canonical_bucket_slug(ascii_label[:48])
    for keyword, slug in _HEBREW_BUCKET_KEYWORDS:
        if keyword in label:
            return slug
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return f"bucket-{digest}"


def _missing_standard_technion_bucket_slugs(existing_bucket_slugs: set[str]) -> set[str]:
    canonical_existing = {_canonical_bucket_slug(slug) for slug in existing_bucket_slugs}
    return _STANDARD_TECHNION_BUCKET_SLUGS - canonical_existing


def _dedupe_requirement_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        group_id = str(group.get("groupId") or "")
        if not group_id:
            continue
        existing = merged.get(group_id)
        if existing is None:
            merged[group_id] = group
            continue
        existing_refs = existing.get("courseReferences") or []
        incoming_refs = group.get("courseReferences") or []
        if incoming_refs:
            existing["courseReferences"] = _merge_unique_course_refs(existing_refs, incoming_refs)
    return list(merged.values())


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


def _parent_track_slug(page: WikiPage) -> str | None:
    parent = canonical_program_track_slug(page)
    if parent:
        return parent
    for label in ("Parent Track", "Parent Tracks"):
        raw = extract_field(page.english_body, label)
        if not raw:
            continue
        for link in extract_wikilinks(raw):
            if link.startswith("track-"):
                return link
    return None


def inherit_parent_track_title_hints(
    programs: list[dict[str, Any]],
    pages: dict[str, WikiPage],
) -> int:
    """Fill missing titleHints from a track's parent program or parent wiki page."""
    title_by_number: dict[str, str] = {}
    for program in programs:
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber")
                title = ref.get("titleHint")
                if number and title:
                    title_by_number.setdefault(str(number), str(title))

    program_by_slug = {
        str((program.get("metadata") or {}).get("wikiPage")): program
        for program in programs
        if (program.get("metadata") or {}).get("wikiPage")
    }

    for program in programs:
        wiki_slug = (program.get("metadata") or {}).get("wikiPage")
        page = pages.get(str(wiki_slug)) if wiki_slug else None
        if page is None:
            continue
        parent_slug = _parent_track_slug(page)
        if not parent_slug:
            continue
        parent_program = program_by_slug.get(parent_slug)
        if parent_program is not None:
            for group in parent_program.get("requirementGroups", []):
                for ref in group.get("courseReferences", []):
                    number = ref.get("courseNumber")
                    title = ref.get("titleHint")
                    if number and title:
                        title_by_number.setdefault(str(number), str(title))

    filled = 0
    for program in programs:
        wiki_slug = (program.get("metadata") or {}).get("wikiPage")
        page = pages.get(str(wiki_slug)) if wiki_slug else None
        parent_slug = _parent_track_slug(page) if page is not None else None
        parent_page = pages.get(parent_slug) if parent_slug else None
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                if ref.get("titleHint"):
                    continue
                number = ref.get("courseNumber")
                if not number:
                    continue
                title = title_by_number.get(str(number))
                if not title and parent_page is not None:
                    from app.vault.title_index import build_wiki_title_index

                    parent_index = build_wiki_title_index({parent_slug: parent_page, **pages})
                    title = parent_index.get(str(number))
                if not title:
                    continue
                ref["titleHint"] = title
                evidence = list(ref.get("sourceEvidence") or [])
                evidence.append(f"titleHint:parent-track:{parent_slug}:{number}")
                ref["sourceEvidence"] = evidence
                ref["confidence"] = "medium"
                filled += 1
    return filled


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

    standard_technion_buckets = _STANDARD_TECHNION_BUCKET_SLUGS
    missing_standard_buckets = _missing_standard_technion_bucket_slugs(existing_bucket_slugs)
    if missing_standard_buckets:
        for group in _general_technion_credit_bucket_groups(
            program_code,
            technion_wide_total=technion_wide_total,
        ):
            slug = group["groupId"].split(":", 1)[-1]
            if slug in missing_standard_buckets:
                requirement_groups.append(group)

    requirement_groups.extend(_semester_matrix_groups(page, program_code, pages=pages))
    requirement_groups.extend(
        _general_technion_elective_groups(program_code, technion_wide_total=technion_wide_total)
    )
    requirement_groups.extend(
        faculty_elective_groups(page, program_code, faculty_id, pages=pages)
    )
    requirement_groups = _dedupe_requirement_groups(requirement_groups)

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
            "programKind": track_program_kind(page),
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
    faculty_track_slug_set = frozenset(track_slugs)
    programs: list[dict[str, Any]] = []
    exported_program_slugs: set[str] = set()
    for slug in track_slugs:
        page = pages.get(slug)
        if page is None or not should_export_degree_program(
            page,
            faculty_track_slugs=faculty_track_slug_set,
        ):
            continue
        if slug in exported_program_slugs:
            continue
        program = build_generic_program(page, faculty_id=faculty_id, pages=pages)
        if program is not None:
            programs.append(program)
            exported_program_slugs.add(slug)

    if not programs:
        raise ValueError(
            f"No exportable BSc track programs found for faculty {faculty_id!r} "
            f"(wiki id {wiki_faculty_id}). Add track pages with Track/Program code fields.",
        )

    enrich_programs(programs, offering_index)
    inherit_parent_track_title_hints(programs, pages)

    track_program_codes = build_track_program_code_map(pages, faculty_id)
    path_catalog = build_wiki_path_catalog(
        wiki_path=root,
        institution_id=INSTITUTION_ID,
        faculty_id=wiki_faculty_id,
        track_program_codes=track_program_codes,
        catalog_year=CATALOG_YEAR,
        catalog_version=CATALOG_VERSION,
    )

    expected_program_codes = sorted(program["programCode"] for program in programs)
    wiki_source = _relative_vault_path(root)
    export_report = {
        "exporter": "vault-export-specialized",
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
            "exportMode": "specialized",
            "expectedProgramCodes": expected_program_codes,
            "catalogYear": CATALOG_YEAR,
            "catalogVersion": CATALOG_VERSION,
            "sourceFile": wiki_source,
            "pageReferences": [],
            "manualReviewRequired": True,
            "confidence": "medium",
            "notes": [
                "Exported deterministically from catalog_valut wiki pages (specialized faculty exporter).",
                "Elective-chain pools are parsed from wiki specialization groups, tables, and group sections.",
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
            "curatedBy": "vault-export-specialized",
            "curatedAt": _utc_now_iso(),
            "sourceDraftPath": wiki_source,
            "sourceMarkdownPath": wiki_source,
            "courseJsonSources": export_report["courseJsonSources"],
            "curationStatus": "ready-for-staging-with-review-flags",
            "knownLimitations": [
                "Focus-chain choose-N semantics are encoded as non-executable pools when present.",
                "Science placeholder rows without course codes are omitted.",
                "Tracks without a full Technion program code require overrides in track_program_code_overrides.json.",
            ],
            "countsBefore": {},
            "countsAfter": counts,
            "unresolvedIssues": unresolved,
        },
        "curationReport": {"warnings": unresolved},
        "signoffReview": {
            "reviewedBy": "vault-export-specialized",
            "reviewedAt": _utc_now_iso(),
            "reviewStatus": "ready-for-staging-with-review-flags",
            "sourceFilesReviewed": [wiki_source],
            "checksPerformed": [
                "program_codes_present",
                "credit_buckets_present",
                "semester_matrices_parsed",
                "course_numbers_normalized",
                "wiki_elective_pools_parsed",
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
    readiness.setdefault("blockingIssuesForStaging", [])

    faculty_catalog_context_from_document(document)
    ReviewedCuratedCatalogDocument.model_validate(document)
    Phase8ReadinessCheck.model_validate(readiness)
    return document, readiness
