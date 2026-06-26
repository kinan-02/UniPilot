"""Tests for the multi-faculty catalog wiki export registry."""

from __future__ import annotations

import pytest

from app.vault.elective_chain_contract import validate_elective_chain_export
from app.vault.loader import wiki_root
from app.vault.vault_export_registry import (
    export_vault_catalog,
    get_faculty_export_spec,
    supported_export_faculties,
)


def test_supported_faculties_includes_dds_and_computer_science():
    faculties = supported_export_faculties()
    assert "dds" in faculties
    assert "computer-science" in faculties


def test_computer_science_export_produces_track_programs():
    document, readiness = export_vault_catalog(vault_path=wiki_root(), faculty="computer-science")
    assert document["source"]["facultyId"] == "computer-science"
    assert document["source"]["exportMode"] == "generic"
    assert len(document["programs"]) >= 1
    assert readiness["canImportToStaging"] is True
    program_codes = {program["programCode"] for program in document["programs"]}
    assert "023023-1-000" in program_codes


def test_unsupported_faculty_raises_with_supported_list():
    with pytest.raises(ValueError, match="Unsupported faculty export: civil"):
        export_vault_catalog(vault_path=wiki_root(), faculty="civil")


def test_dds_export_applies_faculty_scoped_contract():
    document, readiness = export_vault_catalog(vault_path=wiki_root(), faculty="dds")
    violations = validate_elective_chain_export(document, faculty_id="dds")
    assert violations == [], "\n".join(violations)
    assert document["source"]["facultyId"] == "dds"
    assert readiness["canImportToStaging"] is True


def test_validation_skips_faculty_without_contract():
    document = {
        "programs": [{"programCode": "999999-1-000", "requirementGroups": []}],
        "parserReport": {"faculty": "civil"},
    }
    assert validate_elective_chain_export(document) == []


def test_dds_spec_lists_expected_program_codes():
    spec = get_faculty_export_spec("dds")
    assert "009118-1-000" in spec.expected_program_codes
