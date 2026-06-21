"""CI vault fixture export tests (minimal wiki subset, no full catalog_valut/)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.importers.dds_catalog_staging_importer import import_dds_catalog_to_staging
from app.models.catalog import ReviewedCuratedCatalogDocument
from app.models.staging_catalog import Phase8ReadinessCheck
from app.vault.export_dds_catalog import export_vault_catalog, write_vault_catalog_export

CI_VAULT_ROOT = Path(__file__).resolve().parent / "fixtures" / "catalog_vault"
CI_COURSE_JSON = [
    Path(__file__).resolve().parent / "fixtures" / name
    for name in ("courses_2025_200.json", "courses_2025_201.json", "courses_2025_202.json")
]


def test_ci_fixture_exports_three_dds_programs():
    document, readiness = export_vault_catalog(
        vault_path=CI_VAULT_ROOT,
        faculty="dds",
        course_json_paths=CI_COURSE_JSON,
    )
    ReviewedCuratedCatalogDocument.model_validate(document)
    Phase8ReadinessCheck.model_validate(readiness)

    codes = {program["programCode"] for program in document["programs"]}
    assert codes == {"009216-1-000", "009009-1-000", "009118-1-000"}
    assert readiness["canImportToStaging"] is True
    assert document["curationReport"]["vaultSignoff"] is not None
    assert document["signoffReview"]["reviewStatus"] == "vault-signed-ready-for-staging"


def test_ci_fixture_includes_dne_semester_matrix():
    document, _ = export_vault_catalog(
        vault_path=CI_VAULT_ROOT,
        faculty="dds",
        course_json_paths=CI_COURSE_JSON,
    )
    dne = next(item for item in document["programs"] if item["programCode"] == "009216-1-000")
    group_ids = {group["groupId"] for group in dne["requirementGroups"]}
    assert "009216-1-000:semester-1-matrix" in group_ids
    assert "009216-1-000:elective-ds-pool" in group_ids


def test_ci_fixture_enriches_title_from_course_page():
    document, _ = export_vault_catalog(
        vault_path=CI_VAULT_ROOT,
        faculty="dds",
        course_json_paths=CI_COURSE_JSON,
    )
    dne = next(item for item in document["programs"] if item["programCode"] == "009216-1-000")
    semester_one = next(
        group for group in dne["requirementGroups"] if group["groupId"] == "009216-1-000:semester-1-matrix"
    )
    refs = {ref["courseNumber"]: ref for ref in semester_one["courseReferences"]}
    assert refs["00940345"]["titleHint"] == "מתמטיקה דיסקרטית"


def test_ci_fixture_passes_staging_import_dry_run(tmp_path: Path):
    output = tmp_path / "catalog_reviewed.json"
    readiness_path = tmp_path / "readiness.json"
    write_vault_catalog_export(
        vault_path=CI_VAULT_ROOT,
        faculty="dds",
        output_path=output,
        readiness_path=readiness_path,
        course_json_paths=CI_COURSE_JSON,
    )

    summary = import_dds_catalog_to_staging(
        None,
        catalog_path=output,
        readiness_path=readiness_path,
        dry_run=True,
    )
    assert summary.dryRun is True
    assert summary.programsUpserted == 3
    assert summary.requirementsUpserted >= 10


def test_ci_fixture_unsupported_faculty_raises():
    with pytest.raises(ValueError, match="Unsupported faculty"):
        export_vault_catalog(vault_path=CI_VAULT_ROOT, faculty="civil")
