"""Per-faculty elective enrichment registry for specialized vault export."""

from __future__ import annotations

import re
from typing import Any

from app.vault.export_cs_electives import (
    GENERAL_4YEAR_SLUG,
    cs_elective_groups_from_source,
)
from app.vault.export_wiki_elective_groups import wiki_elective_groups
from app.vault.loader import WikiPage, extract_field, extract_wikilinks

_CATALOG_LINK_PATTERN = re.compile(
    r"See\s+\[\[(?P<slug>technion-[a-z0-9-]+)\]\]\s+for\s+(?:full\s+)?elective",
    re.IGNORECASE,
)
_CHOOSE_POOL_OPERATORS = frozenset({"choose_n", "choose_chain"})


def _faculty_id_from_page(page: WikiPage) -> str:
    raw = page.frontmatter.get("faculty")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().removeprefix("faculty-")
    tags = page.frontmatter.get("tags") or []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("faculty-"):
            return tag.removeprefix("faculty-")
    return ""


def _canonical_elective_source_slug(page: WikiPage) -> str | None:
    raw = page.frontmatter.get("canonicalSlug")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    parent_track = extract_field(page.english_body, "Parent Track")
    if parent_track:
        for link in extract_wikilinks(parent_track):
            if link.startswith("track-"):
                return link
    return None


def _extract_program_code(page: WikiPage) -> str | None:
    from app.vault.export_faculty_vault_catalog import extract_program_code

    return extract_program_code(page)


def _resolve_elective_source_slug(page: WikiPage, pages: dict[str, WikiPage]) -> str | None:
    raw = page.frontmatter.get("electiveSource")
    if isinstance(raw, str) and raw.strip():
        slug = raw.strip()
        if slug in pages and slug != page.slug:
            return slug

    canonical = _canonical_elective_source_slug(page)
    if canonical and canonical in pages and canonical != page.slug:
        return canonical

    for label in ("Parent Track", "Parent Tracks"):
        parent_field = extract_field(page.english_body, label)
        if not parent_field:
            continue
        for link in extract_wikilinks(parent_field):
            if link.startswith("track-") and link in pages and link != page.slug:
                return link
    return None


def _resolve_elective_catalog_source(page: WikiPage) -> str | None:
    raw = page.frontmatter.get("electiveCatalogSource")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().removesuffix(".md")

    match = _CATALOG_LINK_PATTERN.search(page.english_body)
    if match:
        return match.group("slug")
    return None


def _group_suffix(group_id: str) -> str:
    return group_id.split(":", 1)[-1] if ":" in group_id else group_id


def _reprefix_groups(groups: list[dict[str, Any]], program_code: str) -> list[dict[str, Any]]:
    reprefixed: list[dict[str, Any]] = []
    for group in groups:
        group_id = str(group.get("groupId") or "")
        if not group_id:
            continue
        suffix = _group_suffix(group_id)
        updated = dict(group)
        updated["groupId"] = f"{program_code}:{suffix}"
        reprefixed.append(updated)
    return reprefixed


def _merge_elective_groups(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in primary + secondary:
        group_id = str(group.get("groupId") or "")
        if not group_id:
            continue
        suffix = _group_suffix(group_id)
        existing = merged.get(suffix)
        if existing is None:
            merged[suffix] = group
            continue
        existing_refs = existing.get("courseReferences") or []
        incoming_refs = group.get("courseReferences") or []
        if len(incoming_refs) > len(existing_refs):
            merged[suffix] = group
    return list(merged.values())


def _choose_pool_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        group
        for group in groups
        if (group.get("ruleExpression") or {}).get("operator") in _CHOOSE_POOL_OPERATORS
        and (group.get("courseReferences") or [])
    ]


def _elective_groups_for_page(
    page: WikiPage,
    program_code: str,
    faculty_id: str,
    *,
    pages: dict[str, WikiPage],
) -> list[dict[str, Any]]:
    if page.slug == "track-data-information-engineering":
        from app.vault.export_dds_catalog import DDS_TRACK_SLUGS, _dne_elective_groups

        config = DDS_TRACK_SLUGS.get(page.slug)
        if config is not None:
            return _dne_elective_groups(page, program_code, config)

    if faculty_id == "computer-science":
        if page.slug == GENERAL_4YEAR_SLUG:
            return cs_elective_groups_from_source(page, program_code)
        return []
    return wiki_elective_groups(page, program_code, faculty_id)


def _credit_bucket_only_groups(page: WikiPage, program_code: str) -> list[dict[str, Any]]:
    """Emit advisory choose_n pool from the first elective markdown table on the page."""
    from app.vault.export_wiki_elective_groups import _table_pool_from_section
    from app.vault.markdown_tables import find_table_with_header

    english = page.english_body
    elective_start = -1
    for marker in ("## Faculty Elective", "## Elective Requirements", "בחירה"):
        pos = english.find(marker)
        if pos >= 0 and (elective_start < 0 or pos < elective_start):
            elective_start = pos
    section = english[elective_start:] if elective_start >= 0 else english
    table = find_table_with_header(section, "Code") or find_table_with_header(section, "קוד")
    if table is None:
        return []
    pool = _table_pool_from_section(
        section,
        page=page,
        program_code=program_code,
        group_suffix="advisory-elective-list-pool",
        title="Advisory elective course list",
        operator="choose_n",
        choose_count=1,
        catalog_description="Advisory elective list parsed from wiki; credits tracked via buckets.",
    )
    return [pool] if pool is not None and (pool.get("courseReferences") or []) else []


def faculty_elective_groups(
    page: WikiPage,
    program_code: str,
    faculty_id: str,
    *,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, Any]]:
    """Apply faculty-specific elective-chain enrichment on top of generic export."""
    page_index = pages or {}
    groups = _elective_groups_for_page(page, program_code, faculty_id, pages=page_index)

    elective_mode = page.frontmatter.get("electiveMode")
    if elective_mode == "credit-bucket-only" and not _choose_pool_groups(groups):
        groups = _merge_elective_groups(groups, _credit_bucket_only_groups(page, program_code))

    catalog_slug = _resolve_elective_catalog_source(page)
    if catalog_slug and catalog_slug in page_index:
        catalog_page = page_index[catalog_slug]
        catalog_faculty = _faculty_id_from_page(catalog_page) or faculty_id
        catalog_groups = wiki_elective_groups(catalog_page, program_code, catalog_faculty)
        groups = _merge_elective_groups(groups, _reprefix_groups(catalog_groups, program_code))

    source_slug = _resolve_elective_source_slug(page, page_index)
    if source_slug and source_slug in page_index:
        source_page = page_index[source_slug]
        source_faculty = _faculty_id_from_page(source_page) or faculty_id
        source_code = _extract_program_code(source_page) or program_code
        inherited = faculty_elective_groups(
            source_page,
            source_code,
            source_faculty,
            pages=page_index,
        )
        groups = _merge_elective_groups(
            groups,
            _reprefix_groups(inherited, program_code),
        )

    return _dual_medicine_pool_overrides(page, program_code, groups, page_index)


def _dual_medicine_pool_overrides(
    page: WikiPage,
    program_code: str,
    groups: list[dict[str, Any]],
    pages: dict[str, WikiPage],
) -> list[dict[str, Any]]:
    if program_code != "027396-1-000":
        return groups

    from app.vault.export_dds_catalog import _course_pool_group, _dne_starred_course_refs

    updated: list[dict[str, Any]] = []
    has_hash_pool = False
    for group in groups:
        copied = dict(group)
        suffix = _group_suffix(str(copied.get("groupId") or ""))
        if suffix == "elective-ds-pool":
            copied["minCredits"] = 11.0
            copied["title"] = "Dual-degree engineering electives"
            notes = list(copied.get("notes") or [])
            notes.append("Must include at least 5.0 credits from the dual DNE list and 1 # project course.")
            copied["notes"] = notes
        if suffix == "dual-hash-project-pool":
            has_hash_pool = True
        updated.append(copied)

    if not has_hash_pool:
        dne_page = pages.get("track-data-information-engineering")
        if dne_page is not None:
            hash_refs = _dne_starred_course_refs({dne_page.slug: dne_page})
            if hash_refs:
                updated.append(
                    _course_pool_group(
                        program_code=program_code,
                        group_suffix="dual-hash-project-pool",
                        title="Dual-degree data-intensive project course",
                        course_refs=hash_refs,
                        rule_expression={
                            "type": "course_pool",
                            "operator": "choose_n",
                            "chooseCount": 1,
                            "chain": "dual_hash_projects",
                        },
                        catalog_description=(
                            "Complete at least one engineering elective marked # "
                            "(data-intensive project course)."
                        ),
                        notes=["At least one # project course required among engineering electives."],
                    )
                )

    return updated
