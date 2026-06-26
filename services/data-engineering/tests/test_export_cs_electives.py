"""Tests for CS elective-chain enrichment."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.vault.export_cs_electives import (
    GENERAL_4YEAR_PROGRAM_CODE,
    GENERAL_4YEAR_SLUG,
    _refs_for_numbers,
    _specialization_section,
    cs_elective_groups,
)
from app.vault.export_faculty_vault_catalog import build_generic_program
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root
from app.paths import catalog_vault_root


def _load_general_4year_page() -> WikiPage:
    root = wiki_root(catalog_vault_root())
    pages = load_pages_by_slug(root)
    return pages[GENERAL_4YEAR_SLUG]


def test_cs_elective_groups_only_for_general_4year_track() -> None:
    page = _load_general_4year_page()
    groups = cs_elective_groups(page, GENERAL_4YEAR_PROGRAM_CODE)
    assert len(groups) == 16
    suffixes = {group["groupId"].split(":", 1)[1] for group in groups}
    assert "cs-science-chain-physics-mm" in suffixes
    assert "cs-spec-group-11" in suffixes

    other_page = WikiPage(
        slug="track-computer-science-cyber",
        path=page.path,
        frontmatter={**page.frontmatter, "title": page.title},
        body=page.body,
        english_body=page.english_body,
    )
    assert cs_elective_groups(other_page, "023023-2-000") == []


def test_build_generic_program_includes_cs_electives() -> None:
    page = _load_general_4year_page()
    program = build_generic_program(page, faculty_id="computer-science", pages={page.slug: page})
    assert program is not None
    group_ids = [group["groupId"] for group in program["requirementGroups"]]
    assert any("cs-spec-group-01" in group_id for group_id in group_ids)


def test_refs_for_numbers_skips_invalid_and_duplicate_refs() -> None:
    with patch("app.vault.export_cs_electives.build_course_reference") as mock_build:
        mock_build.side_effect = [
            None,
            {"courseNumber": "02360313"},
            {"courseNumber": "02360313"},
            {"courseNumber": "02360315"},
        ]
        refs = _refs_for_numbers(
            ("bad", "02360313", "02360313", "02360315"),
            source_page=Path("wiki/tracks/track.md"),
        )
    assert len(refs) == 2
    assert refs[0]["courseNumber"] == "02360313"
    assert refs[1]["courseNumber"] == "02360315"


def test_specialization_section_edge_cases() -> None:
    assert _specialization_section("no specialization here") == ""
    body = "### Specialization Groups\n**1. Foo**\nCourses include: (02360313)\n"
    assert _specialization_section(body) == body
    body_with_rules = body + "## Special Rules\n- rule"
    assert _specialization_section(body_with_rules).endswith("(02360313)\n")
    body_hebrew_end = body + "## נתונים בעברית\nhebrew"
    assert _specialization_section(body_hebrew_end).endswith("(02360313)\n")


def test_cs_elective_groups_returns_empty_when_specialization_section_missing() -> None:
    page = _load_general_4year_page()
    stripped = WikiPage(
        slug=GENERAL_4YEAR_SLUG,
        path=page.path,
        frontmatter=page.frontmatter,
        body=page.body,
        english_body="**Track code:** 023023-1-000\n",
    )
    groups = cs_elective_groups(stripped, GENERAL_4YEAR_PROGRAM_CODE)
    assert len(groups) == 5
    assert all("science-chain" in group["groupId"] for group in groups)
