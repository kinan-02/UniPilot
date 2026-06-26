"""Tests for faculty wiki track → program code resolution."""

from __future__ import annotations

from app.vault.export_faculty_vault_catalog import extract_program_code
from app.vault.faculty_track_program_index import (
    build_faculty_track_program_index,
    normalize_program_code,
    parse_faculty_track_codes,
)
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root
from app.paths import catalog_vault_root
from app.importers.dds_catalog_staging_importer import program_staging_key


def test_program_staging_key_includes_wiki_page_for_concentrations() -> None:
    key = program_staging_key(
        "computer-science",
        "2025-2026",
        "023023-1-000",
        wiki_page="track-computer-science-cyber",
    )
    assert key.endswith(":track-computer-science-cyber")


def test_normalize_program_code_expands_short_codes() -> None:
    assert normalize_program_code("001404") == "001404-1-000"
    assert normalize_program_code("001404-1-000") == "001404-1-000"
    assert normalize_program_code("not-a-code") == "not-a-code"


def test_track_pages_section_stops_at_nested_heading() -> None:
    from app.vault.faculty_track_program_index import _track_slugs_from_track_pages_section

    text = (
        "### Track Pages\n"
        "- [[track-one]]\n"
        "### Graduate Programs\n"
        "- [[track-two]]\n"
    )
    assert _track_slugs_from_track_pages_section(text) == ["track-one"]


def test_clear_faculty_track_program_index_cache() -> None:
    from app.vault.faculty_track_program_index import clear_faculty_track_program_index_cache

    build_faculty_track_program_index()
    clear_faculty_track_program_index_cache()
    assert build_faculty_track_program_index.cache_info().currsize == 0


def test_faculty_table_maps_civil_construction_management() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    faculty = pages["faculty-civil-environmental-engineering"]
    mapping = parse_faculty_track_codes(faculty)
    assert mapping["track-civil-engineering-construction-management"] == "001404-1-000"
    assert mapping["track-civil-engineering-water-transport"] == "001201-1-000"


def test_faculty_table_maps_architecture_inline_links() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    faculty = pages["faculty-architecture-town-planning"]
    mapping = parse_faculty_track_codes(faculty)
    assert mapping["track-architecture"] == "020220-1-000"


def test_extract_program_code_uses_faculty_index_for_missing_field() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-environmental-engineering"]
    assert extract_program_code(page) == "001101-1-000"


def test_build_faculty_track_program_index_includes_overrides() -> None:
    index = build_faculty_track_program_index()
    assert index["track-mechanical-engineering"] == "034034-1-000"
    assert index["track-computer-science-cyber"] == "023023-1-000"


def test_parse_faculty_track_codes_ignores_lines_without_codes() -> None:
    page = WikiPage(
        slug="faculty-test",
        path=wiki_root(catalog_vault_root()),
        frontmatter={},
        body="",
        english_body="| Track | [[track-example]] |\n",
    )
    assert parse_faculty_track_codes(page) == {}
