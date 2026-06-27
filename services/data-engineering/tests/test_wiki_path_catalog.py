"""Tests for wiki path catalog export."""

from __future__ import annotations

from pathlib import Path

from app.paths import catalog_vault_root, resolve_catalog_vault_wiki_root
from app.vault.export_dds_catalog import DDS_TRACK_SLUGS, export_vault_catalog
from app.vault.loader import load_pages_by_slug
from app.vault.wiki_path_catalog import (
    _track_selectable_as_primary,
    _track_study_levels,
    build_wiki_path_catalog,
)

VAULT_ROOT = catalog_vault_root()
WIKI_ROOT = resolve_catalog_vault_wiki_root(VAULT_ROOT)


def test_build_wiki_path_catalog_includes_tracks_programs_and_graduate_areas():
    catalog = build_wiki_path_catalog(
        wiki_path=WIKI_ROOT,
        track_program_codes={slug: config["programCode"] for slug, config in DDS_TRACK_SLUGS.items()},
        catalog_year=2025,
        catalog_version="2025-2026",
    )

    kinds = {option["kind"] for option in catalog["pathOptions"]}
    assert "bsc_track" in kinds
    assert "special_program" in kinds
    assert "minor" in kinds
    assert "graduate_program" in kinds
    assert "dne_specialization" in kinds
    assert len(catalog["faculties"]) >= 1
    assert any(option["wikiSlug"] == "program-excellence" for option in catalog["pathOptions"])

    avivim = next(option for option in catalog["pathOptions"] if option["wikiSlug"] == "program-avivim")
    assert avivim["nameHe"] == 'תוכנית עילית "אביבים"'
    assert avivim["duration"] == "4.5 years"

    dne = next(
        option
        for option in catalog["pathOptions"]
        if option["wikiSlug"] == "track-data-information-engineering"
    )
    assert dne["duration"] == "4 years (8 semesters)"
    assert dne["totalCreditsRequired"] == "155"


def test_medicine_md_is_not_primary_admission_path():
    pages = load_pages_by_slug(WIKI_ROOT)
    md_page = pages["track-medicine-md"]
    assert "MD" in _track_study_levels(md_page)
    assert _track_selectable_as_primary(md_page) is False


def test_chemistry_haznek_includes_bsc_and_msc_levels():
    pages = load_pages_by_slug(WIKI_ROOT)
    haznek = pages["track-chemistry-haznek"]
    levels = _track_study_levels(haznek)
    assert "BSc" in levels
    assert "MSc" in levels


def test_track_selectable_as_primary_ignores_non_continuation_prerequisites():
    pages = load_pages_by_slug(WIKI_ROOT)
    dne = pages["track-data-information-engineering"]
    assert _track_selectable_as_primary(dne) is True

    generic_prereq_page = type(
        "WikiPage",
        (),
        {
            "english_body": "**Prerequisites:** High school diploma.",
            "body": "",
        },
    )()
    assert _track_selectable_as_primary(generic_prereq_page) is True

    non_track_prereq_page = type(
        "WikiPage",
        (),
        {
            "english_body": "**Prerequisites:** Completion of [[program-excellence]].",
            "body": "",
        },
    )()
    assert _track_selectable_as_primary(non_track_prereq_page) is True


def test_export_vault_catalog_attaches_path_catalog():
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    assert len(document["pathOptions"]) >= 15
    assert len(document["faculties"]) >= 1
    primary_bsc = [
        option
        for option in document["pathOptions"]
        if option["kind"] == "bsc_track" and option["selectableAsPrimary"]
    ]
    assert len(primary_bsc) == 3
    graduate_levels = {
        tuple(option["studyLevels"])
        for option in document["pathOptions"]
        if option["kind"] == "graduate_program"
    }
    assert all("BSc" not in levels for levels in graduate_levels)
    slugs = {option["wikiSlug"] for option in document["pathOptions"]}
    assert "grad-ph-d-requirements" not in slugs
    assert all(option["facultyId"] == "faculty-dds" for option in document["pathOptions"])

    dne = next(
        option
        for option in document["pathOptions"]
        if option["wikiSlug"] == "track-data-information-engineering"
    )
    assert dne["nameHe"] == "הנדסת נתונים ומידע"
    description = dne.get("description") or ""
    assert "**Hebrew name:**" not in description
    assert "**Program code:**" not in description
