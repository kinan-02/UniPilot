"""Tests for vault path catalog production parity."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.vault.export_dds_catalog import export_vault_catalog
from app.vault.verify_vault_path_catalog_parity import verify_vault_path_catalog_parity

VAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "catalog_valut"


def test_path_catalog_parity_passes_after_staging_import_shape(mongo_database):
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    settings = get_settings()

    if document.get("faculties"):
        mongo_database[settings.production_catalog_faculties_collection].delete_many({})
        mongo_database[settings.production_catalog_faculties_collection].insert_many(document["faculties"])

    if document.get("pathOptions"):
        mongo_database[settings.production_catalog_path_options_collection].delete_many({})
        mongo_database[settings.production_catalog_path_options_collection].insert_many(document["pathOptions"])

    result = verify_vault_path_catalog_parity(
        mongo_database,
        settings=settings,
        vault_path=VAULT_ROOT,
        faculty="dds",
    )
    assert result.ok is True
    assert result.missing_path_options == []
    assert result.field_mismatches == []
