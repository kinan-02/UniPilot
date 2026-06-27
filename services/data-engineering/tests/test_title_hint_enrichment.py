"""Tests for titleHint enrichment helpers."""

from __future__ import annotations

from pathlib import Path

from app.utils.course_numbers import title_hint_from_wikilink_cell
from app.vault.export_faculty_vault_catalog import inherit_parent_track_title_hints
from app.vault.loader import WikiPage
from app.vault.title_index import build_wiki_title_index
from app.vault.vault_export_registry import export_vault_catalog


def test_title_hint_from_wikilink_cell_uses_display_text() -> None:
    cell = "[[02360315-algebraic-methods-cs|שיטות אלגבריות במדעי המחשב]]"
    assert title_hint_from_wikilink_cell(cell) == "שיטות אלגבריות במדעי המחשב"


def test_title_hint_from_wikilink_cell_uses_linked_page_title() -> None:
    page = WikiPage(
        slug="02360315-algebraic-methods-cs",
        path=Path("/tmp/02360315.md"),
        frontmatter={"title_he": "שיטות אלגבריות"},
        body="",
        english_body="",
    )
    cell = "[[02360315-algebraic-methods-cs|02360315]]"
    assert title_hint_from_wikilink_cell(cell, pages={page.slug: page}) == "שיטות אלגבריות"


def test_title_hint_from_wikilink_cell_prefers_name_column() -> None:
    cell = "[[02360315-algebraic-methods-cs|02360315]]"
    assert title_hint_from_wikilink_cell(cell, fallback_name="From Column") == "From Column"


def test_wiki_title_index_reads_wikilink_alias_in_body() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="Elective: [[02360999-missing-page|שם קורס בעברית]]",
    )
    index = build_wiki_title_index({page.slug: page})
    assert index.get("02360999") == "שם קורס בעברית"


def test_wiki_title_index_reads_wikilink_alias() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="| Code | Credits |\n|---|---|\n| [[02360315-algebraic-methods-cs|שיטות אלגבריות]] | 3 |",
    )
    index = build_wiki_title_index({page.slug: page})
    assert index["02360315"] == "שיטות אלגבריות"


def test_inherit_parent_track_title_hints_fills_child_refs() -> None:
    parent_page = WikiPage(
        slug="track-parent",
        path=Path("/tmp/parent.md"),
        frontmatter={},
        body="",
        english_body="**Parent Track:** [[track-parent]]",
    )
    child_page = WikiPage(
        slug="track-child",
        path=Path("/tmp/child.md"),
        frontmatter={},
        body="",
        english_body="**Parent Track:** [[track-parent]]",
    )
    programs = [
        {
            "metadata": {"wikiPage": "track-parent"},
            "requirementGroups": [
                {
                    "courseReferences": [
                        {"courseNumber": "02360315", "titleHint": "שיטות אלגבריות במדעי המחשב"},
                    ]
                }
            ],
        },
        {
            "metadata": {"wikiPage": "track-child"},
            "requirementGroups": [
                {
                    "courseReferences": [
                        {"courseNumber": "02360315", "titleHint": None, "sourceEvidence": []},
                    ]
                }
            ],
        },
    ]
    filled = inherit_parent_track_title_hints(programs, {"track-parent": parent_page, "track-child": child_page})
    assert filled == 1
    child_ref = programs[1]["requirementGroups"][0]["courseReferences"][0]
    assert child_ref["titleHint"] == "שיטות אלגבריות במדעי המחשב"


def test_title_hint_from_wikilink_cell_returns_none_without_match() -> None:
    assert title_hint_from_wikilink_cell("02360315") is None


def test_title_hint_from_wikilink_cell_skips_numeric_alias() -> None:
    page = WikiPage(
        slug="02360315-algebraic-methods-cs",
        path=Path("/tmp/02360315.md"),
        frontmatter={"title_he": "שיטות אלגבריות"},
        body="",
        english_body="",
    )
    cell = "[[missing-slug|02360315]]"
    assert title_hint_from_wikilink_cell(cell, pages={page.slug: page}) is None


def test_wiki_title_index_uses_linked_course_page_slug() -> None:
    course_page = WikiPage(
        slug="02360315-algebraic-methods-cs",
        path=Path("/tmp/02360315.md"),
        frontmatter={"course_code": "02360315", "title_he": "שיטות אלגבריות"},
        body="",
        english_body="| Code |\n|---|\n| [[02360315-algebraic-methods-cs|02360315]] |",
    )
    index = build_wiki_title_index({course_page.slug: course_page})
    assert index["02360315"] == "שיטות אלגבריות"


def test_inherit_parent_track_title_hints_uses_canonical_slug() -> None:
    child_page = WikiPage(
        slug="track-child",
        path=Path("/tmp/child.md"),
        frontmatter={"canonicalSlug": "track-parent"},
        body="",
        english_body="",
    )
    parent_page = WikiPage(
        slug="track-parent",
        path=Path("/tmp/parent.md"),
        frontmatter={},
        body="",
        english_body="שיטות אלגבריות במדעי המחשב (02360315)",
    )
    programs = [
        {
            "metadata": {"wikiPage": "track-child"},
            "requirementGroups": [
                {"courseReferences": [{"courseNumber": "02360315", "titleHint": None, "sourceEvidence": []}]}
            ],
        }
    ]
    filled = inherit_parent_track_title_hints(
        programs,
        {"track-child": child_page, "track-parent": parent_page},
    )
    assert filled == 1


def test_inherit_parent_track_title_hints_skips_missing_page_and_number() -> None:
    programs = [
        {
            "metadata": {"wikiPage": "missing-track"},
            "requirementGroups": [
                {"courseReferences": [{"courseNumber": None, "titleHint": None}]},
            ],
        }
    ]
    assert inherit_parent_track_title_hints(programs, {}) == 0


def test_parent_track_slug_reads_parent_tracks_label() -> None:
    from app.vault.export_faculty_vault_catalog import _parent_track_slug

    page = WikiPage(
        slug="track-child",
        path=Path("/tmp/child.md"),
        frontmatter={},
        body="",
        english_body="**Parent Tracks:** [[track-parent]] (primary)",
    )
    assert _parent_track_slug(page) == "track-parent"


def test_export_readiness_counts_match_post_signoff_document() -> None:
    document, readiness = export_vault_catalog(faculty="dds")
    missing_in_doc = sum(
        1
        for program in document["programs"]
        for group in program["requirementGroups"]
        for ref in group.get("courseReferences") or []
        if not ref.get("titleHint")
    )
    assert readiness["counts"]["missingTitleHints"] == missing_in_doc
