"""Tests for elective inheritance and catalog-source enrichment."""

from __future__ import annotations

from pathlib import Path

from app.vault.export_cs_electives import cs_elective_groups_from_source
from app.vault.export_dds_catalog import DDS_TRACK_SLUGS, _dne_elective_groups
from app.vault.faculty_elective_enrichers import faculty_elective_groups
from app.vault.loader import WikiPage


def _page(
    slug: str,
    *,
    english: str = "",
    frontmatter: dict | None = None,
) -> WikiPage:
    return WikiPage(
        slug=slug,
        path=Path(f"/tmp/{slug}.md"),
        frontmatter=frontmatter or {},
        body=english,
        english_body=english,
    )


def test_cs_elective_groups_from_source_repairs_program_code() -> None:
    parent = _page(
        "track-computer-science-general-4year",
        english="### Specialization Groups\n**1. Algorithms**\n02360315\n",
        frontmatter={"faculty": "faculty-computer-science"},
    )
    child = _page(
        "track-computer-science-general-3year",
        frontmatter={
            "faculty": "faculty-computer-science",
            "electiveSource": "track-computer-science-general-4year",
        },
        english="**Track code:** 023044-1-000",
    )
    pages = {parent.slug: parent, child.slug: child}
    groups = faculty_elective_groups(
        child,
        "023044-1-000",
        "computer-science",
        pages=pages,
    )
    choose_pools = [
        group
        for group in groups
        if (group.get("ruleExpression") or {}).get("operator") in {"choose_n", "choose_chain"}
    ]
    assert choose_pools
    assert all(str(group["groupId"]).startswith("023044-1-000:") for group in choose_pools)


def test_cs_elective_groups_from_source_returns_empty_for_non_source_page() -> None:
    page = _page("track-computer-science-general-3year")
    assert cs_elective_groups_from_source(page, "023044-1-000", source_page=page) == []


def test_dne_elective_groups_exports_choose_n_list_pool() -> None:
    page = _page(
        "track-data-information-engineering",
        english=(
            "## DNE Elective Course List\n\n"
            "| Code | Name (Hebrew) | Notes |\n"
            "|------|--------------|-------|\n"
            "| [[00960222-language-computation-and-cogni|0960222]] | שפה | **\\*** |\n"
            "| [[00960262-information-retrieval|0960262]] | אחזור | |\n"
        ),
    )
    config = DDS_TRACK_SLUGS["track-data-information-engineering"]
    groups = _dne_elective_groups(page, "009216-1-000", config)
    choose_pool = next(
        group
        for group in groups
        if str(group.get("groupId", "")).endswith(":dne-elective-list-pool")
    )
    assert (choose_pool.get("ruleExpression") or {}).get("operator") == "choose_n"
    assert len(choose_pool.get("courseReferences") or []) == 2


def test_faculty_elective_groups_inherits_nested_source_chain() -> None:
    grandparent = _page(
        "track-materials-engineering",
        english=(
            "## Faculty Elective Courses (מקצועות בחירה פקולטית)\n\n"
            "| Code | Course | Credits |\n"
            "|---|---|---|\n"
            "| [[03140111-example|03140111]] | Example | 3.0 |\n"
        ),
        frontmatter={"faculty": "faculty-materials-science-engineering"},
    )
    child = _page(
        "track-materials-engineering-biology",
        frontmatter={
            "faculty": "faculty-materials-science-engineering",
            "electiveSource": "track-materials-engineering",
        },
        english="**Program code:** 031313-1-000",
    )
    pages = {grandparent.slug: grandparent, child.slug: child}
    groups = faculty_elective_groups(
        child,
        "031313-1-000",
        "materials-science-engineering",
        pages=pages,
    )
    assert any(str(group["groupId"]).startswith("031313-1-000:") for group in groups)


def test_faculty_elective_groups_resolves_parent_track_link() -> None:
    parent = _page(
        "track-computer-science-general-4year",
        english="### Specialization Groups\n**1. Algorithms**\n02360315\n",
        frontmatter={"faculty": "faculty-computer-science"},
    )
    child = _page(
        "track-computer-science-cyber",
        english="**Parent Track:** [[track-computer-science-general-4year]]",
        frontmatter={"faculty": "faculty-computer-science"},
    )
    pages = {parent.slug: parent, child.slug: child}
    groups = faculty_elective_groups(
        child,
        "023023-1-000",
        "computer-science",
        pages=pages,
    )
    assert groups


def test_faculty_elective_groups_credit_bucket_only_mode() -> None:
    from app.vault.faculty_elective_enrichers import _credit_bucket_only_groups

    page = _page(
        "track-chemistry-haznek",
        english=(
            "## Faculty Elective Requirements\n\n"
            "| Code | Course | Credits |\n"
            "|---|---|---|\n"
            "| [[01270450-biophotochemistry-quantum-phenomena|01270450]] | Bio | 2.0 |\n"
        ),
        frontmatter={"faculty": "faculty-chemistry", "electiveMode": "credit-bucket-only"},
    )
    groups = _credit_bucket_only_groups(page, "012154-1-000")
    assert groups
    assert groups[0]["groupId"].endswith(":advisory-elective-list-pool")


def test_faculty_elective_groups_parses_catalog_link_without_frontmatter() -> None:
    catalog = _page(
        "technion-education-catalog-2025-2026",
        english="## Faculty Elective Requirements\n| Code | Course |\n|---|---|\n| 00440105 | Circuits |\n",
        frontmatter={"faculty": "faculty-education-science-technology"},
    )
    track = _page(
        "track-education-electronics-electricity",
        english="See [[technion-education-catalog-2025-2026]] for full elective lists.",
        frontmatter={"faculty": "faculty-education-science-technology"},
    )
    pages = {catalog.slug: catalog, track.slug: track}
    groups = faculty_elective_groups(
        track,
        "021025-1-000",
        "education-science-technology",
        pages=pages,
    )
    assert groups


def test_faculty_elective_groups_uses_elective_catalog_source_frontmatter() -> None:
    catalog = _page(
        "technion-civil-catalog-2025-2026",
        english="## Faculty Elective Requirements\n| Code | Course |\n|---|---|\n| 00140615 | Finance |\n",
        frontmatter={"faculty": "faculty-civil-environmental-engineering"},
    )
    track = _page(
        "track-environmental-engineering",
        frontmatter={
            "faculty": "faculty-civil-environmental-engineering",
            "electiveCatalogSource": "technion-civil-catalog-2025-2026",
        },
        english="**Program code:** 001101-1-000",
    )
    pages = {catalog.slug: catalog, track.slug: track}
    groups = faculty_elective_groups(
        track,
        "001101-1-000",
        "civil-environmental-engineering",
        pages=pages,
    )
    assert groups


def test_faculty_elective_groups_applies_credit_bucket_mode_when_no_pools() -> None:
    page = _page(
        "track-example",
        english=(
            "## Program notes\n\n"
            "| Code | Course | Credits |\n"
            "|---|---|---|\n"
            "| [[01270450-biophotochemistry-quantum-phenomena|01270450]] | Bio | 2.0 |\n"
        ),
        frontmatter={"faculty": "faculty-chemistry", "electiveMode": "credit-bucket-only"},
    )
    groups = faculty_elective_groups(page, "012154-1-000", "chemistry", pages={page.slug: page})
    assert any(str(group.get("groupId", "")).endswith(":advisory-elective-list-pool") for group in groups)


def test_faculty_elective_enricher_helpers() -> None:
    from app.vault.faculty_elective_enrichers import (
        _choose_pool_groups,
        _faculty_id_from_page,
        _merge_elective_groups,
        _reprefix_groups,
        _resolve_elective_source_slug,
    )

    tagged = _page("track-tagged", frontmatter={"tags": ["faculty-physics"]})
    assert _faculty_id_from_page(tagged) == "physics"
    assert _faculty_id_from_page(_page("track-none")) == ""

    parentless = _page(
        "track-child",
        english="**Parent Track:** not-a-track",
        frontmatter={"canonicalSlug": "track-missing"},
    )
    assert _resolve_elective_source_slug(parentless, {}) is None

    merged = _merge_elective_groups(
        [{"groupId": "001:pool-a", "courseReferences": [{"courseNumber": "1"}]}],
        [
            {"groupId": "001:pool-a", "courseReferences": [{"courseNumber": "1"}, {"courseNumber": "2"}]},
            {"groupId": "", "courseReferences": [{"courseNumber": "9"}]},
        ],
    )
    assert len(merged) == 1
    assert len(merged[0]["courseReferences"]) == 2

    reprefixed = _reprefix_groups(
        [
            {"groupId": "009216-1-000:dne-elective-list-pool", "courseReferences": []},
            {"groupId": "", "courseReferences": [{"courseNumber": "1"}]},
        ],
        "027396-1-000",
    )
    assert reprefixed[0]["groupId"] == "027396-1-000:dne-elective-list-pool"

    choose_only = _choose_pool_groups(
        [
            {"groupId": "x:y", "ruleExpression": {"operator": "choose_n"}, "courseReferences": [{}]},
            {"groupId": "x:z", "ruleExpression": {"operator": "min_credits"}, "courseReferences": [{}]},
            {"groupId": "x:w", "ruleExpression": {"operator": "choose_n"}, "courseReferences": []},
        ]
    )
    assert len(choose_only) == 1


def test_faculty_elective_groups_resolves_parent_tracks_plural_field() -> None:
    parent = _page(
        "track-mechanical-engineering",
        english=(
            "## Elective Requirements — Advanced Courses (32.5 נק')\n\n"
            "### רשימה א — קורסים חישוביים\n"
            "| Course | Code | Credits |\n"
            "|--------|------|---------|\n"
            "| Finite elements | [[00350022-finite-elements-engineering-analysis|00350022]] | 3.0 |\n"
        ),
        frontmatter={"faculty": "faculty-mechanical-engineering"},
    )
    child = _page(
        "track-mechanical-engineering-barak",
        english="**Parent Tracks:** [[track-mechanical-engineering]]",
        frontmatter={"faculty": "faculty-mechanical-engineering"},
    )
    pages = {parent.slug: parent, child.slug: child}
    groups = faculty_elective_groups(
        child,
        "034034-2-000",
        "mechanical-engineering",
        pages=pages,
    )
    assert groups


def test_credit_bucket_only_groups_returns_empty_without_table() -> None:
    from app.vault.faculty_elective_enrichers import _credit_bucket_only_groups

    page = _page("track-empty", english="No tables here.")
    assert _credit_bucket_only_groups(page, "012154-1-000") == []


def test_faculty_elective_groups_inherits_dne_list_for_medicine_dual() -> None:
    dne = _page(
        "track-data-information-engineering",
        english=(
            "## DNE Elective Course List\n\n"
            "| Code | Name (Hebrew) | Notes |\n"
            "|------|--------------|-------|\n"
            "| [[00960262-information-retrieval|0960262]] | IR | |\n"
        ),
        frontmatter={"faculty": "faculty-dds"},
    )
    dual = _page(
        "track-medicine-dual-data-information-engineering",
        frontmatter={
            "faculty": "faculty-medicine",
            "electiveSource": "track-data-information-engineering",
        },
        english="**Program code:** 027396-1-000",
    )
    pages = {dne.slug: dne, dual.slug: dual}
    groups = faculty_elective_groups(
        dual,
        "027396-1-000",
        "medicine",
        pages=pages,
    )
    assert any(str(group.get("groupId", "")).endswith(":dne-elective-list-pool") for group in groups)

    dne = _page(
        "track-data-information-engineering",
        english=(
            "## DNE Elective Course List\n\n"
            "| Code | Name (Hebrew) | Notes |\n"
            "|------|--------------|-------|\n"
            "| [[00960262-information-retrieval|0960262]] | IR | |\n"
        ),
        frontmatter={"faculty": "faculty-dds"},
    )
    dual = _page(
        "track-medicine-dual-data-information-engineering",
        frontmatter={
            "faculty": "faculty-medicine",
            "electiveSource": "track-data-information-engineering",
        },
        english="**Program code:** 027396-1-000",
    )
    pages = {dne.slug: dne, dual.slug: dual}
    groups = faculty_elective_groups(
        dual,
        "027396-1-000",
        "medicine",
        pages=pages,
    )
    assert any(str(group.get("groupId", "")).endswith(":dne-elective-list-pool") for group in groups)
