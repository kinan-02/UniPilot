"""Verify production path catalog collections match the wiki vault export."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pymongo.database import Database

from app.config import Settings, get_settings
from app.vault.export_dds_catalog import export_vault_catalog

PUBLISHED_STATUS_FILTER = {"status": "published"}


@dataclass
class PathCatalogParityMismatch:
    option_key: str
    field: str
    expected: Any
    actual: Any


@dataclass
class PathCatalogParityResult:
    status: Literal["pass", "fail"]
    wiki_root: str
    exported_at: str
    expected_faculty_count: int
    expected_path_option_count: int
    production_faculty_count: int
    production_path_option_count: int
    missing_faculties: list[str] = field(default_factory=list)
    extra_faculties: list[str] = field(default_factory=list)
    missing_path_options: list[str] = field(default_factory=list)
    extra_path_options: list[str] = field(default_factory=list)
    field_mismatches: list[PathCatalogParityMismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "pass"


COMPARE_FIELDS = (
    "facultyId",
    "wikiSlug",
    "kind",
    "nameHe",
    "studyLevels",
    "selectableAsPrimary",
    "linkedProgramCode",
    "duration",
    "totalCreditsRequired",
)


def _faculty_key(doc: dict[str, Any]) -> str:
    return str(doc.get("facultyId") or doc.get("wikiSlug") or "")


def _path_option_key(doc: dict[str, Any]) -> str:
    return str(doc.get("optionKey") or "")


def verify_vault_path_catalog_parity(
    database: Database,
    *,
    settings: Settings | None = None,
    vault_path: Path | None = None,
    faculty: str = "dds",
) -> PathCatalogParityResult:
    settings = settings or get_settings()
    document, _ = export_vault_catalog(vault_path=vault_path, faculty=faculty)

    expected_faculties = {
        _faculty_key(item): item for item in document.get("faculties") or [] if _faculty_key(item)
    }
    expected_options = {
        _path_option_key(item): item
        for item in document.get("pathOptions") or []
        if _path_option_key(item)
    }

    production_faculties: dict[str, dict[str, Any]] = {}
    for doc in database[settings.production_catalog_faculties_collection].find(PUBLISHED_STATUS_FILTER):
        key = _faculty_key(doc)
        if key:
            production_faculties[key] = doc

    production_options: dict[str, dict[str, Any]] = {}
    for doc in database[settings.production_catalog_path_options_collection].find(PUBLISHED_STATUS_FILTER):
        key = _path_option_key(doc)
        if key:
            production_options[key] = doc

    missing_faculties = sorted(set(expected_faculties) - set(production_faculties))
    extra_faculties = sorted(set(production_faculties) - set(expected_faculties))
    missing_path_options = sorted(set(expected_options) - set(production_options))
    extra_path_options = sorted(set(production_options) - set(expected_options))

    field_mismatches: list[PathCatalogParityMismatch] = []
    for option_key, expected in expected_options.items():
        actual = production_options.get(option_key)
        if actual is None:
            continue
        for field_name in COMPARE_FIELDS:
            expected_value = expected.get(field_name)
            actual_value = actual.get(field_name)
            if expected_value != actual_value:
                field_mismatches.append(
                    PathCatalogParityMismatch(
                        option_key=option_key,
                        field=field_name,
                        expected=expected_value,
                        actual=actual_value,
                    )
                )

    status: Literal["pass", "fail"] = (
        "pass"
        if not missing_faculties
        and not extra_faculties
        and not missing_path_options
        and not extra_path_options
        and not field_mismatches
        else "fail"
    )

    return PathCatalogParityResult(
        status=status,
        wiki_root=str(vault_path or "data/catalog_valut"),
        exported_at=datetime.now(UTC).isoformat(),
        expected_faculty_count=len(expected_faculties),
        expected_path_option_count=len(expected_options),
        production_faculty_count=len(production_faculties),
        production_path_option_count=len(production_options),
        missing_faculties=missing_faculties,
        extra_faculties=extra_faculties,
        missing_path_options=missing_path_options,
        extra_path_options=extra_path_options,
        field_mismatches=field_mismatches,
    )
