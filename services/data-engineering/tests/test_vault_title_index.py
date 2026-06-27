"""Tests for wiki title index building."""

from __future__ import annotations

from pathlib import Path

from app.paths import catalog_vault_root
from app.vault.loader import load_pages_by_slug, wiki_root
from app.vault.title_index import build_wiki_title_index

VAULT_ROOT = catalog_vault_root()


def test_wiki_title_index_includes_table_and_inline_titles():
    pages = load_pages_by_slug(wiki_root(VAULT_ROOT))
    index = build_wiki_title_index(pages)
    assert index.get("00960244") == "מתודולוגיות מחקר בעיבוד שפה טבעית"
    assert index.get("002160035") or index.get("02160035")


def test_wiki_title_index_includes_course_pages():
    pages = load_pages_by_slug(wiki_root(VAULT_ROOT))
    index = build_wiki_title_index(pages)
    assert "00940345" in index
    assert index.get("02360315") == "שיטות אלגבריות במדעי המחשב"


def test_wiki_title_index_reads_reverse_inline_titles() -> None:
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="Courses include: שיטות אלגבריות במדעי המחשב (02360315)",
    )
    index = build_wiki_title_index({page.slug: page})
    assert index["02360315"] == "שיטות אלגבריות במדעי המחשב"


def test_wiki_title_index_indexes_entity_course_pages() -> None:
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="02360315-algebraic-methods-cs",
        path=Path("/tmp/02360315-algebraic-methods-cs.md"),
        frontmatter={
            "type": "entity",
            "course_code": 940197,
            "title_he": "פרויקט מחקר סמסטריאלי",
            "title": "00940197 — Semester Research Project",
        },
        body="",
        english_body="",
    )
    index = build_wiki_title_index({page.slug: page})
    assert index["00940197"] == "פרויקט מחקר סמסטריאלי"


def test_wiki_title_index_reads_course_column_header() -> None:
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body=(
            "| Code | Course | Credits |\n"
            "|---|---|---|\n"
            "| 00140411 | Soil Engineering | 3.5 |\n"
        ),
    )
    index = build_wiki_title_index({page.slug: page})
    assert index["00140411"] == "Soil Engineering"
