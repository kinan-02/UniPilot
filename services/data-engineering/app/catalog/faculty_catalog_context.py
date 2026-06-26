"""Faculty-scoped catalog validation context for staging, quality, and promotion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PROGRAM_CODE_PATTERN = re.compile(r"^0\d{5}-\d-\d{3}$")


@dataclass(frozen=True)
class FacultyCatalogContext:
    faculty_id: str
    source_name: str
    source_type: str
    expected_program_codes: tuple[str, ...]
    export_mode: str

    @property
    def production_key_prefix(self) -> str:
        return f"technion-{self.faculty_id}"


def _normalize_faculty_id(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return str(raw).strip().lower().replace("_", "-")


def faculty_id_from_document(document: dict[str, Any]) -> str:
    source = document.get("source") or {}
    faculty_id = source.get("facultyId")
    if faculty_id:
        return _normalize_faculty_id(faculty_id)
    parser = document.get("parserReport") or {}
    if parser.get("faculty"):
        return _normalize_faculty_id(parser["faculty"])
    programs = document.get("programs") or []
    if programs:
        metadata = (programs[0].get("metadata") or {})
        wiki_faculty = metadata.get("facultyId") or metadata.get("faculty")
        if wiki_faculty:
            wiki = str(wiki_faculty)
            if wiki.startswith("faculty-"):
                return _normalize_faculty_id(wiki.removeprefix("faculty-"))
            return _normalize_faculty_id(wiki)
    return "dds"


def expected_program_codes_from_document(document: dict[str, Any]) -> tuple[str, ...]:
    source = document.get("source") or {}
    explicit = source.get("expectedProgramCodes")
    if explicit:
        return tuple(str(code) for code in explicit)
    programs = document.get("programs") or []
    return tuple(str(program["programCode"]) for program in programs if program.get("programCode"))


def faculty_catalog_context_from_document(document: dict[str, Any]) -> FacultyCatalogContext:
    faculty_id = faculty_id_from_document(document)
    source = document.get("source") or {}
    export_mode = str(source.get("exportMode") or "specialized")
    source_type = str(source.get("sourceType") or f"{faculty_id}_catalog_curated_reviewed")
    source_name = str(source.get("sourceName") or f"technion-{faculty_id}-catalog")
    return FacultyCatalogContext(
        faculty_id=faculty_id,
        source_name=source_name,
        source_type=source_type,
        expected_program_codes=expected_program_codes_from_document(document),
        export_mode=export_mode,
    )


def faculty_catalog_context_from_staging_program(staging: dict[str, Any]) -> FacultyCatalogContext | None:
    metadata = staging.get("metadata") or {}
    faculty_raw = metadata.get("facultyId") or metadata.get("faculty")
    if not faculty_raw:
        source_name = staging.get("sourceName") or ""
        if source_name.startswith("technion-") and source_name.endswith("-catalog"):
            faculty_id = source_name.removeprefix("technion-").removesuffix("-catalog")
            return FacultyCatalogContext(
                faculty_id=faculty_id,
                source_name=source_name,
                source_type=str(staging.get("sourceType") or f"{faculty_id}_catalog_curated_reviewed"),
                expected_program_codes=(str(staging.get("programCode")),)
                if staging.get("programCode")
                else tuple(),
                export_mode="generic",
            )
        return None
    faculty_id = _normalize_faculty_id(str(faculty_raw).removeprefix("faculty-"))
    return FacultyCatalogContext(
        faculty_id=faculty_id,
        source_name=str(staging.get("sourceName") or f"technion-{faculty_id}-catalog"),
        source_type=str(staging.get("sourceType") or f"{faculty_id}_catalog_curated_reviewed"),
        expected_program_codes=(str(staging.get("programCode")),) if staging.get("programCode") else tuple(),
        export_mode=str((staging.get("sourceMetadata") or {}).get("exportMode") or "generic"),
    )


def production_program_key(faculty_id: str, program_code: str, catalog_version: str) -> str:
    return f"technion-{faculty_id}:program:{program_code}:{catalog_version}"


def production_requirement_key(faculty_id: str, group_id: str, catalog_version: str) -> str:
    return f"technion-{faculty_id}:requirement:{group_id}:{catalog_version}"


def production_advisory_requirement_key(faculty_id: str, group_id: str, catalog_version: str) -> str:
    return f"technion-{faculty_id}:advisory-rule:req:{group_id}:{catalog_version}"
