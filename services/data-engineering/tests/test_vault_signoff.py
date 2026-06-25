"""Tests for vault wiki-backed catalog sign-off."""

from __future__ import annotations

import json
from pathlib import Path

from app.vault.export_dds_catalog import export_vault_catalog

from app.paths import catalog_vault_root

VAULT_ROOT = catalog_vault_root()


def test_vault_signoff_derives_non_executable_groups():
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    derived = document["curationReport"]["vaultSignoff"]["signedOffNonExecutableRuleGroupIds"]
    assert len(derived) >= 30
    assert "009216-1-000:semester-1-matrix" in derived
    assert "009216-1-000:core-mandatory" not in derived


def test_vault_signoff_marks_production_exclusions():
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    vault = document["curationReport"]["vaultSignoff"]
    assert vault["signoffSource"] == "vault-wiki"
    assert vault["enforceNonExecutableRulesInProduction"] is False
    assert vault["nonExecutableRulesPolicy"] == "advisory-only"
    assert vault.get("ingestibleCourseScope") == "dds-faculty-semester-json"
    assert len(vault["productionExcludedCourseNumbers"]) >= 10
    assert "01040042" in vault["productionExcludedCourseNumbers"]
    assert len(vault["signedOffNonExecutableRuleGroupIds"]) >= 30


def test_apply_vault_signoff_adds_source_refs():
    document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    program = next(item for item in document["programs"] if item["programCode"] == "009216-1-000")
    assert program.get("wikiSourceRefs")
    assert any(ref.get("sourceType") == "catalog_vault_wiki" for ref in program["wikiSourceRefs"])


def test_readiness_includes_vault_signoff():
    document, readiness = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
    assert readiness["canImportToStaging"] is True
    assert readiness.get("vaultSignoff")
    assert document["signoffReview"]["reviewStatus"] == "vault-signed-ready-for-staging"
