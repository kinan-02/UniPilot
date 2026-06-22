"""Tests for catalog wiki vault export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.importers.dds_catalog_staging_importer import import_dds_catalog_to_staging
from app.models.catalog import ReviewedCuratedCatalogDocument
from app.models.staging_catalog import Phase8ReadinessCheck
from app.vault.export_dds_catalog import export_vault_catalog, write_vault_catalog_export
from app.vault.loader import load_wiki_page
from app.vault.markdown_tables import parse_markdown_tables


VAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "catalog_valut"
TRACK_PAGE = (
    VAULT_ROOT / "wiki" / "entities" / "track-data-information-engineering.md"
)


def test_load_dne_track_page_frontmatter():
    page = load_wiki_page(TRACK_PAGE)
    assert page.slug == "track-data-information-engineering"
    assert page.title_he == "הנדסת נתונים ומידע"
    assert "Semester 1" in page.english_body
    assert "## נתונים בעברית" in page.body


def test_parse_semester_table_from_track_page():
    page = load_wiki_page(TRACK_PAGE)
    tables = parse_markdown_tables(page.english_body)
    assert tables
    semester_one = next(
        table
        for table in tables
        if any(row and row[0].startswith("0940345") for row in table.rows)
    )
    assert "0940345" in semester_one.rows[0][0]


def test_export_vault_catalog_builds_three_programs():
    document, readiness = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    ReviewedCuratedCatalogDocument.model_validate(document)
    Phase8ReadinessCheck.model_validate(readiness)

    codes = {program["programCode"] for program in document["programs"]}
    assert codes == {"009216-1-000", "009009-1-000", "009118-1-000"}
    assert readiness["canImportToStaging"] is True
    assert document["curationReport"]["vaultSignoff"] is not None
    assert readiness["canImportToStaging"] is True
    assert document["signoffReview"]["reviewStatus"] == "vault-signed-ready-for-staging"


def test_export_includes_dne_semester_and_elective_groups():
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    dne = next(item for item in document["programs"] if item["programCode"] == "009216-1-000")
    group_ids = {group["groupId"] for group in dne["requirementGroups"]}
    assert "009216-1-000:semester-1-matrix" in group_ids
    assert "009216-1-000:elective-ds-pool" in group_ids
    assert "009216-1-000:cognition-track:requirements" in group_ids


def test_export_includes_ie_is_choose_n_eligible_courses():
    from app.vault.export_dds_catalog import _iem_elective_groups, _is_elective_groups
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root())
    iem = pages["track-industrial-engineering-management"]
    ise = pages["track-information-systems-engineering"]

    iem_groups = {g["groupId"].split(":")[-1]: g for g in _iem_elective_groups(iem, "009009-1-000")}
    assert len(iem_groups["ie-statistics-elective-chain"]["courseReferences"]) == 8
    assert len(iem_groups["ie-behavior-science-chain"]["courseReferences"]) == 2
    assert iem_groups["ie-statistics-elective-chain"].get("catalogDescription")
    assert iem_groups["ie-behavior-science-chain"].get("catalogDescription")
    assert "ie-focus-chain-game-theory" in iem_groups
    assert "ie-focus-chain-advanced-industry" in iem_groups
    assert "ie-focus-chain-operations-research" in iem_groups
    assert iem_groups["ie-focus-chain-game-theory"].get("catalogDescription")
    assert len(iem_groups["ie-focus-chain-operations-research"]["courseReferences"]) <= 6

    ise_groups = {g["groupId"].split(":")[-1]: g for g in _is_elective_groups(ise, "009118-1-000", pages)}
    assert len(ise_groups["is-behavior-science-chain"]["courseReferences"]) == 2
    numbers = {ref["courseNumber"] for ref in ise_groups["is-behavior-science-chain"]["courseReferences"]}
    assert numbers == {"00960600", "00960620"}
    assert ise_groups["is-behavior-science-chain"].get("catalogDescription")
    ml_refs = {ref["courseNumber"] for ref in ise_groups["is-focus-chain-ml"]["courseReferences"]}
    assert len(ml_refs) > 4
    assert "00970215" in ml_refs


def test_export_passes_staging_import_dry_run(tmp_path: Path):
    output = tmp_path / "catalog_reviewed.json"
    readiness_path = tmp_path / "readiness.json"
    write_vault_catalog_export(
        vault_path=VAULT_ROOT,
        faculty="dds",
        output_path=output,
        readiness_path=readiness_path,
    )

    summary = import_dds_catalog_to_staging(
        None,
        catalog_path=output,
        readiness_path=readiness_path,
        dry_run=True,
    )
    assert summary.dryRun is True
    assert summary.programsUpserted == 3
    assert summary.requirementsUpserted >= 30


def test_unsupported_faculty_raises():
    from app.vault.vault_export_registry import export_vault_catalog as registry_export

    with pytest.raises(ValueError, match="Unsupported faculty"):
        registry_export(vault_path=VAULT_ROOT, faculty="civil")
