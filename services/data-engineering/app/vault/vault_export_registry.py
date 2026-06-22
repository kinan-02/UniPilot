"""Technion catalog wiki vault export registry — one entry point per faculty."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.vault.elective_chain_contract import (
    apply_elective_chain_violations,
    validate_elective_chain_export,
)
from app.vault.vault_signoff import finalize_export_quality_metadata

VaultExportFn = Callable[..., tuple[dict[str, Any], dict[str, Any]]]


@dataclass(frozen=True)
class FacultyVaultExportSpec:
    faculty_id: str
    expected_program_codes: frozenset[str]
    export: VaultExportFn


def _load_dds_spec() -> FacultyVaultExportSpec:
    from app.vault.export_dds_catalog import export_dds_vault_catalog

    return FacultyVaultExportSpec(
        faculty_id="dds",
        expected_program_codes=frozenset({"009216-1-000", "009009-1-000", "009118-1-000"}),
        export=export_dds_vault_catalog,
    )


_FACULTY_SPECS: dict[str, FacultyVaultExportSpec] | None = None


def faculty_export_specs() -> dict[str, FacultyVaultExportSpec]:
    global _FACULTY_SPECS
    if _FACULTY_SPECS is None:
        dds_spec = _load_dds_spec()
        _FACULTY_SPECS = {dds_spec.faculty_id: dds_spec}
    return _FACULTY_SPECS


def supported_export_faculties() -> tuple[str, ...]:
    return tuple(sorted(faculty_export_specs()))


def get_faculty_export_spec(faculty: str) -> FacultyVaultExportSpec:
    faculty_id = faculty.lower()
    spec = faculty_export_specs().get(faculty_id)
    if spec is None:
        supported = ", ".join(supported_export_faculties()) or "(none registered)"
        raise ValueError(
            f"Unsupported faculty export: {faculty}. "
            f"Register a FacultyVaultExportSpec in vault_export_registry. Supported: {supported}"
        )
    return spec


def export_vault_catalog(
    *,
    vault_path: Path | None = None,
    faculty: str = "dds",
    course_json_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Export a faculty catalog from the wiki vault and apply shared contract gates."""
    spec = get_faculty_export_spec(faculty)
    document, readiness = spec.export(
        vault_path=vault_path,
        course_json_paths=course_json_paths,
    )

    violations = validate_elective_chain_export(document, faculty_id=spec.faculty_id)
    if violations:
        apply_elective_chain_violations(document, violations)

    finalize_export_quality_metadata(document)

    return document, readiness
