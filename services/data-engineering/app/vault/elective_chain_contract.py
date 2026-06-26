"""Shared elective-chain invariants for export, staging quality, and regression tests.

Contracts are scoped per Technion faculty under data/contracts/elective_chain_pools.json.
When a new faculty is onboarded, add a faculties.<id> block and register its exporter in
vault_export_registry.py — validation runs automatically for that faculty only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.paths import service_root


def contract_path() -> Path:
    return service_root() / "data" / "contracts" / "elective_chain_pools.json"


def _normalize_contract(raw: dict[str, Any]) -> dict[str, Any]:
    if "faculties" in raw:
        return raw
    return {
        "version": raw.get("version", 1),
        "institutionId": raw.get("institutionId", "technion"),
        "description": raw.get("description", ""),
        "faculties": {
            "dds": {
                "deprecatedPoolSuffixes": raw.get("deprecatedPoolSuffixes") or [],
                "pools": raw.get("pools") or [],
            }
        },
    }


@lru_cache(maxsize=1)
def load_elective_chain_contract() -> dict[str, Any]:
    return _normalize_contract(json.loads(contract_path().read_text(encoding="utf-8")))


def contracted_faculty_ids() -> tuple[str, ...]:
    contract = load_elective_chain_contract()
    return tuple(sorted((contract.get("faculties") or {}).keys()))


def faculty_contract(faculty_id: str) -> dict[str, Any] | None:
    contract = load_elective_chain_contract()
    return (contract.get("faculties") or {}).get(faculty_id.lower())


def iter_contract_pools(*, faculty_id: str | None = None) -> list[dict[str, Any]]:
    contract = load_elective_chain_contract()
    faculties = contract.get("faculties") or {}
    if faculty_id is not None:
        section = faculties.get(faculty_id.lower())
        return list((section or {}).get("pools") or [])

    pools: list[dict[str, Any]] = []
    for section in faculties.values():
        pools.extend(section.get("pools") or [])
    return pools


def resolve_document_faculty(document: dict[str, Any]) -> str | None:
    report = document.get("parserReport") or {}
    faculty = report.get("faculty")
    if faculty:
        return str(faculty).lower()

    source = document.get("source") or {}
    faculty = source.get("facultyId")
    if faculty:
        return str(faculty).lower()

    for program in document.get("programs") or []:
        metadata = program.get("metadata") or {}
        faculty = metadata.get("faculty")
        if faculty:
            return str(faculty).lower()
    return None


def _group_index(program: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(group.get("groupId", "")).split(":")[-1]: group
        for group in program.get("requirementGroups") or []
        if group.get("groupId")
    }


def _programs_by_code_and_track(
    document: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[tuple[str, str], dict[str, Any]]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    by_code_track: dict[tuple[str, str], dict[str, Any]] = {}
    for program in document.get("programs") or []:
        code = str(program.get("programCode") or "")
        by_code.setdefault(code, []).append(program)
        wiki_page = (program.get("metadata") or {}).get("wikiPage")
        if wiki_page:
            by_code_track[(code, str(wiki_page))] = program
    return by_code, by_code_track


def _resolve_program_for_entry(
    entry: dict[str, Any],
    *,
    by_code: dict[str, list[dict[str, Any]]],
    by_code_track: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    program_code = str(entry["programCode"])
    suffix = str(entry["suffix"])
    track_slug = str(entry.get("trackSlug") or "") or None

    if track_slug:
        program = by_code_track.get((program_code, track_slug))
        if program is not None:
            return program

    candidates = by_code.get(program_code) or []
    if len(candidates) == 1:
        return candidates[0]

    for program in candidates:
        if suffix in _group_index(program):
            return program

    return None if track_slug else (candidates[0] if candidates else None)


def _validate_pools_for_faculty(
    document: dict[str, Any],
    *,
    faculty_id: str,
    pools: list[dict[str, Any]],
    deprecated: set[str],
) -> list[str]:
    violations: list[str] = []
    by_code, by_code_track = _programs_by_code_and_track(document)

    for entry in pools:
        program_code = str(entry["programCode"])
        suffix = str(entry["suffix"])
        program = _resolve_program_for_entry(entry, by_code=by_code, by_code_track=by_code_track)
        if program is None:
            track_hint = f" ({entry['trackSlug']})" if entry.get("trackSlug") else ""
            violations.append(f"missing program {program_code}{track_hint} for pool {suffix}")
            continue

        groups = _group_index(program)
        if suffix in deprecated:
            violations.append(f"deprecated pool still exported: {program_code}:{suffix}")
            continue

        group = groups.get(suffix)
        if group is None:
            violations.append(f"missing pool group {program_code}:{suffix}")
            continue

        operator = (group.get("ruleExpression") or {}).get("operator")
        if operator != entry.get("operator"):
            violations.append(
                f"{program_code}:{suffix} operator={operator!r} expected {entry.get('operator')!r}"
            )

        refs = group.get("courseReferences") or []
        ref_count = len(refs)
        min_refs = int(entry.get("minCourseRefs") or 0)
        max_refs = int(entry.get("maxCourseRefs") or 9999)
        if ref_count < min_refs or ref_count > max_refs:
            violations.append(
                f"{program_code}:{suffix} has {ref_count} course refs (expected {min_refs}-{max_refs})"
            )

        if entry.get("requiresCatalogDescription") and not group.get("catalogDescription"):
            violations.append(f"{program_code}:{suffix} missing catalogDescription")

        ref_numbers = {str(ref.get("courseNumber") or "") for ref in refs}
        for number in entry.get("mustIncludeCourseNumbers") or []:
            normalized = str(number).zfill(8) if len(str(number)) <= 8 else str(number)
            if normalized not in ref_numbers and str(number) not in ref_numbers:
                violations.append(f"{program_code}:{suffix} missing required course {number}")

    for program in document.get("programs") or []:
        program_code = str(program.get("programCode") or "")
        for suffix in deprecated:
            if suffix in _group_index(program):
                violations.append(f"deprecated pool still exported: {program_code}:{suffix}")

    return violations


def validate_elective_chain_export(
    document: dict[str, Any],
    *,
    faculty_id: str | None = None,
) -> list[str]:
    """Return human-readable violations; empty list means explorer-safe for the scoped faculty."""
    resolved_faculty = (faculty_id or resolve_document_faculty(document) or "").lower()
    if not resolved_faculty:
        return []

    section = faculty_contract(resolved_faculty)
    if section is None:
        return []

    pools = section.get("pools") or []
    deprecated = set(section.get("deprecatedPoolSuffixes") or [])
    return _validate_pools_for_faculty(
        document,
        faculty_id=resolved_faculty,
        pools=pools,
        deprecated=deprecated,
    )


def validate_elective_chain_export_all_faculties(document: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for faculty_id in contracted_faculty_ids():
        violations.extend(validate_elective_chain_export(document, faculty_id=faculty_id))
    return violations


def apply_elective_chain_violations(document: dict[str, Any], violations: list[str]) -> None:
    if not violations:
        return
    curation = document.setdefault("curationMetadata", {})
    unresolved = list(curation.get("unresolvedIssues") or [])
    for item in violations:
        if item not in unresolved:
            unresolved.append(item)
    curation["unresolvedIssues"] = unresolved
    report = document.setdefault("curationReport", {})
    warnings = list(report.get("warnings") or [])
    for item in violations:
        if item not in warnings:
            warnings.append(item)
    report["warnings"] = warnings


def validate_staging_requirement_group(requirement_doc: dict[str, Any]) -> list[str]:
    """Validate a single staging degree_requirement_group against the contract."""
    group = requirement_doc.get("requirementGroup") or {}
    group_id = str(group.get("groupId") or "")
    if not group_id:
        return []

    suffix = group_id.split(":")[-1]
    program_code = group_id.split(":")[0] if ":" in group_id else ""
    wiki_page = str(
        (requirement_doc.get("metadata") or {}).get("wikiPage")
        or (requirement_doc.get("programMetadata") or {}).get("wikiPage")
        or ""
    )
    matching_entries = [
        item
        for item in iter_contract_pools()
        if item.get("suffix") == suffix and item.get("programCode") == program_code
    ]
    if wiki_page:
        entry = next(
            (item for item in matching_entries if item.get("trackSlug") == wiki_page),
            None,
        )
    else:
        entry = matching_entries[0] if len(matching_entries) == 1 else None
    if entry is None and len(matching_entries) == 1:
        entry = matching_entries[0]
    if entry is None:
        return []

    violations: list[str] = []
    refs = group.get("courseReferences") or []
    ref_count = len(refs)
    min_refs = int(entry.get("minCourseRefs") or 0)
    max_refs = int(entry.get("maxCourseRefs") or 9999)
    if ref_count < min_refs or ref_count > max_refs:
        violations.append(f"staging {group_id} has {ref_count} refs (expected {min_refs}-{max_refs})")

    if entry.get("requiresCatalogDescription") and not group.get("catalogDescription"):
        violations.append(f"staging {group_id} missing catalogDescription")

    if requirement_doc.get("treatsCoursesAsMandatory"):
        violations.append(f"staging {group_id} treats chain courses as mandatory")

    return violations
