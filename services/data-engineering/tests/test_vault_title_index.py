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
