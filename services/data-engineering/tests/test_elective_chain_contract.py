"""Regression tests for the shared elective chain contract."""

from __future__ import annotations

from app.vault.elective_chain_contract import (
    contracted_faculty_ids,
    load_elective_chain_contract,
    validate_elective_chain_export,
)
from app.vault.export_dds_catalog import export_vault_catalog
from app.vault.loader import load_pages_by_slug, wiki_root


def test_contract_defines_all_ie_is_chain_pools():
    contract = load_elective_chain_contract()
    dds = contract.get("faculties", {}).get("dds", {})
    suffixes = {entry["suffix"] for entry in dds.get("pools") or []}
    assert "ie-focus-chain" not in suffixes
    assert {
        "ie-statistics-elective-chain",
        "ie-behavior-science-chain",
        "ie-focus-chain-game-theory",
        "ie-focus-chain-advanced-industry",
        "ie-focus-chain-operations-research",
        "is-behavior-science-chain",
        "is-focus-chain-performance",
        "is-focus-chain-ml",
        "is-focus-chain-game-theory",
    } <= suffixes


def test_contract_is_scoped_to_technion_dds():
    assert "dds" in contracted_faculty_ids()


def test_validation_skips_uncontracted_faculty_export():
    document = {
        "programs": [],
        "parserReport": {"faculty": "civil"},
    }
    assert validate_elective_chain_export(document) == []


def test_live_vault_export_satisfies_elective_chain_contract():
    document, readiness = export_vault_catalog(vault_path=wiki_root(), faculty="dds")
    violations = validate_elective_chain_export(document)
    assert violations == [], "\n".join(violations)
    assert readiness["canImportToStaging"] is True


def test_ie_focus_chains_do_not_include_group_four_course_flood():
    pages = load_pages_by_slug(wiki_root())
    from app.vault.export_dds_catalog import _iem_elective_groups

    iem = pages["track-industrial-engineering-management"]
    groups = {g["groupId"].split(":")[-1]: g for g in _iem_elective_groups(iem, "009009-1-000")}
    assert len(groups["ie-focus-chain-operations-research"]["courseReferences"]) <= 8
    assert len(groups["ie-focus-chain-game-theory"]["courseReferences"]) <= 10


def test_is_ml_chain_includes_dne_starred_sample():
    pages = load_pages_by_slug(wiki_root())
    from app.vault.export_dds_catalog import _is_elective_groups

    ise = pages["track-information-systems-engineering"]
    groups = {g["groupId"].split(":")[-1]: g for g in _is_elective_groups(ise, "009118-1-000", pages)}
    numbers = {ref["courseNumber"] for ref in groups["is-focus-chain-ml"]["courseReferences"]}
    assert "00970215" in numbers
