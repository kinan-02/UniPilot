"""Tests for wiki-driven elective enrichment."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.paths import catalog_vault_root, service_root
from app.vault.export_faculty_vault_catalog import build_generic_program, extract_program_code
from app.vault.export_wiki_elective_groups import (
    _group_n_pools,
    _parse_specialization_groups,
    _refs_for_numbers,
    _specialization_section,
    _table_pool_from_section,
    collect_contract_pool_entries,
    faculty_pool_prefix,
    wiki_elective_groups,
)
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root
from app.vault.track_program_codes import load_track_program_code_overrides, resolve_program_code


def test_faculty_pool_prefix_known_faculties() -> None:
    assert faculty_pool_prefix("electrical-computer-engineering") == "ece"
    assert faculty_pool_prefix("unknown-faculty-name") == "unknown"


def test_electrical_engineering_track_exports_specialization_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-electrical-engineering"]
    program = build_generic_program(
        page,
        faculty_id="electrical-computer-engineering",
        pages=pages,
    )
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "ece-spec-group-01" in suffixes
    assert "ece-lab-courses-pool" in suffixes
    assert "ece-faculty-elective-list-pool" in suffixes


def test_mathematics_track_exports_science_chain_pool() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-mathematics-bsc"]
    groups = wiki_elective_groups(page, "010040-1-000", "mathematics")
    suffixes = {group["groupId"].split(":", 1)[1] for group in groups}
    assert "math-science-elective-chain" in suffixes


def test_track_program_code_override_for_mechanical() -> None:
    page = WikiPage(
        slug="track-mechanical-engineering",
        path=Path("/tmp/track-mechanical-engineering.md"),
        frontmatter={},
        body="",
        english_body="**Program code:** 03\n",
    )
    assert extract_program_code(page) == "034034-1-000"
    assert resolve_program_code(page, None) == "034034-1-000"


def test_load_track_program_code_overrides_missing_file(monkeypatch, tmp_path) -> None:
    from app.vault.faculty_track_program_index import clear_faculty_track_program_index_cache

    monkeypatch.setattr(
        "app.vault.faculty_track_program_index.overrides_path",
        lambda: tmp_path / "missing.json",
    )
    clear_faculty_track_program_index_cache()
    assert load_track_program_code_overrides() == {}
    clear_faculty_track_program_index_cache()


def test_collect_contract_pool_entries_from_program() -> None:
    document = {
        "programs": [
            {
                "programCode": "004004-1-000",
                "metadata": {"wikiPage": "track-electrical-engineering"},
                "requirementGroups": [
                    {
                        "groupId": "004004-1-000:ece-spec-group-01",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": "00440334"}],
                        "catalogDescription": "Group 1",
                        "notes": ["Mandatory: 00440334 and 00460005"],
                    },
                    {
                        "groupId": "004004-1-000:enrichment-pool",
                        "ruleExpression": {"operator": "min_credits"},
                        "courseReferences": [],
                    },
                ],
            }
        ]
    }
    entries = collect_contract_pool_entries(document, faculty_id="electrical-computer-engineering")
    assert len(entries) == 1
    assert entries[0]["suffix"] == "ece-spec-group-01"
    assert "00440334" in entries[0]["mustIncludeCourseNumbers"]


def test_specialization_section_finds_ece_heading() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    section = _specialization_section(pages["track-electrical-engineering"].english_body)
    assert "Computer Networks" in section


def test_specialization_section_returns_tail_when_no_end_marker() -> None:
    body = "### Specialization Groups\n**1. Foo**\n00440334\n"
    assert _specialization_section(body) == body


def test_refs_for_numbers_skips_invalid_and_duplicates() -> None:
    with patch("app.vault.export_wiki_elective_groups.build_course_reference") as mock_build:
        mock_build.side_effect = [
            None,
            {"courseNumber": "00440334"},
            {"courseNumber": "00440334"},
            {"courseNumber": "00460005"},
        ]
        refs = _refs_for_numbers(
            ("bad", "00440334", "00440334", "00460005"),
            source_page=Path("wiki/tracks/track.md"),
        )
    assert len(refs) == 2


def test_table_pool_from_section_returns_none_without_refs() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="",
    )
    assert (
        _table_pool_from_section(
            "no courses here",
            page=page,
            program_code="004004-1-000",
            group_suffix="ece-test-pool",
            title="Test pool",
            operator="choose_n",
        )
        is None
    )


def test_group_n_pools_parses_dds_iem_track() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-industrial-engineering-management"]
    groups = _group_n_pools(page, "009009-1-000", faculty_id="dds")
    suffixes = {group["groupId"].split(":", 1)[1] for group in groups}
    assert "dds-group-1-elective-chain" in suffixes


def test_parse_specialization_groups_uses_minimum_courses_line() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="",
    )
    section = "### 1. Networks\nMinimum courses: 4\n00440334\n"
    groups = _parse_specialization_groups(
        section,
        program_code="004004-1-000",
        page=page,
        faculty_id="electrical-computer-engineering",
    )
    assert groups[0]["ruleExpression"]["chooseCount"] == 4


def test_specialization_section_stops_at_faculty_elective_heading() -> None:
    body = "### Specialization Groups\n**1. Foo**\n00440334\n## Faculty Elective Courses\nlater"
    section = _specialization_section(body)
    assert "Faculty Elective" not in section


def test_table_pool_from_section_choose_n_operator() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="",
    )
    pool = _table_pool_from_section(
        "| Code | Course |\n|---|---|\n| 00440334 | Networks |\n",
        page=page,
        program_code="004004-1-000",
        group_suffix="ece-test-pool",
        title="Test pool",
        operator="choose_n",
        choose_count=2,
    )
    assert pool is not None
    assert pool["ruleExpression"]["operator"] == "choose_n"


def test_table_pool_from_section_returns_none_for_empty_section() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="",
    )
    assert (
        _table_pool_from_section(
            "",
            page=page,
            program_code="004004-1-000",
            group_suffix="ece-test-pool",
            title="Test pool",
            operator="min_credits",
        )
        is None
    )


def test_group_n_pools_skips_groups_without_course_refs() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="Group 1\n| Code | Course |\n|---|---|\n| TBD | placeholder |\n",
    )
    assert _group_n_pools(page, "004004-1-000", faculty_id="ece") == []


def test_mechanical_track_exports_hebrew_elective_lists() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-mechanical-engineering"]
    program = build_generic_program(page, faculty_id="mechanical-engineering", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "mech-elective-list-א-pool" in suffixes
    assert "mech-elective-list-ה-pool" in suffixes
    list_aleph = [
        group
        for group in program["requirementGroups"]
        if group["groupId"].endswith("mech-elective-list-א-pool")
    ]
    assert len(list_aleph) == 1


def test_hebrew_list_source_uses_body_when_english_has_no_lists() -> None:
    from app.vault.export_wiki_elective_groups import (
        _HEBREW_LIST_HEADER,
        _hebrew_list_source,
        _wiki_elective_body,
    )

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="### רשימה א\n| Code | Course |\n|---|---|\n| 00340123 | sample |\n",
        english_body="## Overview\n",
    )
    assert "### רשימה א" in _hebrew_list_source(page)
    assert _wiki_elective_body(page, _HEBREW_LIST_HEADER) == page.body


def test_wiki_elective_body_prefers_english_when_header_present() -> None:
    from app.vault.export_wiki_elective_groups import _HEBREW_GROUP_HEADER, _wiki_elective_body

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="#### קבוצה א\n- 00140107 sample\n",
        english_body="#### קבוצה א\n- 00140108 sample\n",
    )
    assert _wiki_elective_body(page, _HEBREW_GROUP_HEADER) == page.english_body


def test_specialization_track_elective_pools_skip_sections_without_electives() -> None:
    from app.vault.export_wiki_elective_groups import _specialization_track_elective_pools

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="### Specialization 1 — Test Track\n**Mandatory courses only**\n",
    )
    assert _specialization_track_elective_pools(page, "001201-1-000", faculty_id="civil-environmental-engineering") == []


def test_dedupe_pool_groups_keeps_richest_course_pool() -> None:
    from app.vault.export_wiki_elective_groups import _dedupe_pool_groups

    sparse = {
        "groupId": "010040-1-000:math-elective-list-א-pool",
        "courseReferences": [{"courseNumber": "01040001"}],
    }
    rich = {
        "groupId": "010040-1-000:math-elective-list-א-pool",
        "courseReferences": [{"courseNumber": "01040001"}, {"courseNumber": "01040002"}],
    }
    deduped = _dedupe_pool_groups([sparse, rich, {"courseReferences": []}])
    assert len(deduped) == 1
    assert len(deduped[0]["courseReferences"]) == 2


def test_collect_contract_pool_entries_dedupes_by_program_and_suffix() -> None:
    document = {
        "programs": [
            {
                "programCode": "004004-1-000",
                "metadata": {"wikiPage": "track-test"},
                "requirementGroups": [
                    {
                        "groupId": "004004-1-000:ece-spec-group-01",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": "00440334"}],
                        "catalogDescription": "Group 1",
                        "notes": ["Parsed deterministically from wiki elective section."],
                    },
                    {
                        "groupId": "004004-1-000:ece-spec-group-01",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [
                            {"courseNumber": "00440334"},
                            {"courseNumber": "00440335"},
                        ],
                        "catalogDescription": "Group 1 duplicate",
                    },
                ],
            }
        ]
    }
    entries = collect_contract_pool_entries(document, faculty_id="electrical-computer-engineering")
    assert len(entries) == 1
    assert entries[0]["maxCourseRefs"] == 2


def test_collect_contract_pool_entries_ignores_non_mandatory_notes() -> None:
    document = {
        "programs": [
            {
                "programCode": "004004-1-000",
                "metadata": {"wikiPage": "track-test"},
                "requirementGroups": [
                    {
                        "groupId": "004004-1-000:ece-spec-group-01",
                        "ruleExpression": {"operator": "choose_n"},
                        "courseReferences": [{"courseNumber": "00440334"}],
                        "catalogDescription": "Group 1",
                        "notes": ["Parsed deterministically from wiki elective section."],
                    }
                ],
            }
        ]
    }
    entries = collect_contract_pool_entries(document, faculty_id="electrical-computer-engineering")
    assert "mustIncludeCourseNumbers" not in entries[0]


def test_civil_structures_exports_hebrew_group_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-civil-engineering-structures"]
    program = build_generic_program(
        page,
        faculty_id="civil-environmental-engineering",
        pages=pages,
    )
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "civil-hebrew-group-א-pool" in suffixes
    assert "civil-hebrew-group-ב-pool" in suffixes


def test_civil_water_transport_exports_specialization_elective_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-civil-engineering-water-transport"]
    program = build_generic_program(
        page,
        faculty_id="civil-environmental-engineering",
        pages=pages,
    )
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "civil-spec-1-elective-pool" in suffixes
    assert "civil-spec-2-elective-pool" in suffixes


def test_biology_general_faculty_electives_use_choose_n_operator() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-biology-general"]
    program = build_generic_program(page, faculty_id="biology", pages=pages)
    assert program is not None
    pool = next(
        group
        for group in program["requirementGroups"]
        if group["groupId"].endswith("biology-faculty-elective-list-pool")
    )
    assert pool["ruleExpression"]["operator"] == "choose_n"
    assert len(pool["courseReferences"]) >= 7


def test_aerospace_exports_cluster_elective_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-aerospace-engineering"]
    program = build_generic_program(page, faculty_id="aerospace-engineering", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "aero-cluster-1-elective-pool" in suffixes
    assert "aero-cluster-7-elective-pool" in suffixes


def test_physics_exports_numeric_hebrew_elective_lists() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-physics-three-year"]
    program = build_generic_program(page, faculty_id="physics", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "physics-elective-list-1-pool" in suffixes
    assert "physics-elective-list-3-pool" in suffixes


def test_architecture_exports_elective_subsection_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-architecture"]
    program = build_generic_program(
        page,
        faculty_id="architecture-town-planning",
        pages=pages,
    )
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert any("arch-elective-social-sciences-electives" in suffix for suffix in suffixes)
    assert any("arch-elective-technology-and-sciences-electives" in suffix for suffix in suffixes)


def test_chemistry_exports_hebrew_elective_subsections() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-chemistry-chemistry"]
    program = build_generic_program(page, faculty_id="chemistry", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "chemistry-hebrew-elective-א-pool" in suffixes
    assert "chemistry-hebrew-elective-ב-pool" in suffixes


def test_biomedical_exports_named_elective_groups() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-biomedical-engineering"]
    program = build_generic_program(page, faculty_id="biomedical-engineering", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "bme-elective-group-1-pool" in suffixes
    assert "bme-elective-group-4-pool" in suffixes


def test_biotech_exports_track_cluster_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-biotechnology-food-engineering"]
    program = build_generic_program(
        page,
        faculty_id="biotechnology-food-engineering",
        pages=pages,
    )
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert "biotech-track-a-theory-cluster-pool" in suffixes
    assert "biotech-track-a-experience-and-research-cluster-pool" in suffixes


def test_chemical_engineering_exports_track_scoped_list_pools() -> None:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-chemical-engineering"]
    program = build_generic_program(page, faculty_id="chemical-engineering", pages=pages)
    assert program is not None
    suffixes = {group["groupId"].split(":", 1)[1] for group in program["requirementGroups"]}
    assert any("chem-track-general-list-1-pool" in suffix for suffix in suffixes)
    assert any("chem-track-materials-list-2-pool" in suffix for suffix in suffixes)


def test_bold_numbered_list_pools_without_track_sections() -> None:
    from app.vault.export_wiki_elective_groups import _bold_numbered_list_pools

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**List 1 — Statistics:**\n- 00940481 sample — 4.0 credits\n",
    )
    pools = _bold_numbered_list_pools(page, "005004-1-000", faculty_id="chemical-engineering")
    assert len(pools) == 1
    assert pools[0]["groupId"].endswith("chem-list-1-pool")
