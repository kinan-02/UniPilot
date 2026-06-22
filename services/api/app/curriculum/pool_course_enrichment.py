"""Expand course_pool documents to match catalog vault semantics for the explorer."""

from __future__ import annotations

import re
from typing import Any

FACULTY_ELECTIVE_PREFIXES: tuple[str, ...] = ("0094", "0095", "0096", "0097")
EXPLORER_PREFIX_QUERY_LIMIT = 500

KNOWN_POOL_PREFIXES_BY_SUFFIX: dict[str, tuple[str, ...]] = {
    "elective-faculty-pool": FACULTY_ELECTIVE_PREFIXES,
    "ie-additional-faculty-electives": FACULTY_ELECTIVE_PREFIXES,
    "is-additional-faculty-electives": FACULTY_ELECTIVE_PREFIXES,
}

# Vault: faculty electives include the full DNE elective list plus prefix courses.
INCLUDED_POOL_SUFFIXES: dict[str, str] = {
    "elective-faculty-pool": "elective-ds-pool",
}

# Vault: IE/IS Group 4/3 always allow course 2160035 in addition to prefix rules.
ALWAYS_INCLUDE_NUMBERS_BY_SUFFIX: dict[str, tuple[str, ...]] = {
    "ie-additional-faculty-electives": ("2160035",),
    "is-additional-faculty-electives": ("2160035",),
}

# Vault: choose-N elective chains (eligible options, not mandatory flattening).
CHOOSE_N_CHAIN_FALLBACK_NUMBERS: dict[str, tuple[str, ...]] = {
    "ie-statistics-elective-chain": (
        "0960414",
        "0960415",
        "0960425",
        "0960450",
        "0960465",
        "0960475",
        "0970414",
        "0970449",
    ),
    "ie-behavior-science-chain": ("0960600", "0960620"),
    "is-behavior-science-chain": ("0960600", "0960620"),
}

# Vault focus-chain course numbers (from focus-chains.md) when staging export is empty.
FOCUS_CHAIN_FALLBACK_NUMBERS: dict[str, tuple[str, ...]] = {
    "is-focus-chain-performance": (
        "0960327",
        "0960324",
        "0980413",
        "0960311",
        "0960335",
        "0960351",
        "0970135",
        "0970280",
        "0970325",
        "0970334",
    ),
    "is-focus-chain-ml": (
        "0970209",
        "0960212",
        "0960327",
        "0970414",
        "0960222",
        "0960231",
        "0960235",
        "0960262",
        "0960324",
        "0960693",
        "0970135",
        "0970200",
        "0970215",
        "0970216",
        "0970222",
        "0970247",
        "0970248",
        "0970272",
        "0970400",
    ),
    "is-focus-chain-game-theory": (
        "0960226",
        "0960578",
        "0970317",
        "0960606",
        "0960617",
        "0960690",
    ),
    "ie-focus-chain-game-theory": (
        "0960226",
        "0960570",
        "0960578",
        "0970317",
        "0960606",
        "0960617",
        "0960690",
        "0960211",
    ),
    "ie-focus-chain-advanced-industry": (
        "0960411",
        "0940222",
        "0950111",
        "0960210",
        "0970247",
        "0960208",
        "0960266",
        "0960625",
        "0970139",
        "0960135",
        "0970244",
    ),
    "ie-focus-chain-operations-research": (
        "0960327",
        "0960570",
        "0980413",
        "0960311",
        "0960335",
    ),
}

_PREFIX_TOKEN_PATTERN = re.compile(r"0?9[4-7]")


def normalize_catalog_prefix(prefix: str) -> str:
    token = prefix.strip()
    if len(token) == 3 and token.isdigit():
        return f"0{token}"
    return token


def _pool_suffix(requirement_group_id: str, program_code: str) -> str:
    prefix = f"{program_code}:"
    if requirement_group_id.startswith(prefix):
        return requirement_group_id[len(prefix) :]
    return requirement_group_id


def _prefixes_from_notes(notes: list[Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for note in notes:
        for token in _PREFIX_TOKEN_PATTERN.findall(str(note)):
            normalized = normalize_catalog_prefix(token[-3:] if len(token) > 3 else token)
            if normalized not in seen:
                seen.add(normalized)
                found.append(normalized)
    return found


def resolve_pool_allowed_prefixes(
    pool_document: dict[str, Any],
    *,
    program_code: str,
) -> list[str]:
    rule = pool_document.get("ruleExpression") or {}
    explicit = [
        normalize_catalog_prefix(str(prefix))
        for prefix in (rule.get("allowedPrefixes") or [])
        if prefix
    ]
    if explicit:
        return explicit

    group_id = str(pool_document.get("requirementGroupId") or "")
    suffix = _pool_suffix(group_id, program_code)
    known = KNOWN_POOL_PREFIXES_BY_SUFFIX.get(suffix)
    if known:
        return list(known)

    return _prefixes_from_notes(pool_document.get("notes") or [])


def resolve_included_pool_suffix(pool_document: dict[str, Any], *, program_code: str) -> str | None:
    rule = pool_document.get("ruleExpression") or {}
    explicit = rule.get("includesPoolSuffix")
    if isinstance(explicit, str) and explicit:
        return explicit

    group_id = str(pool_document.get("requirementGroupId") or "")
    suffix = _pool_suffix(group_id, program_code)
    return INCLUDED_POOL_SUFFIXES.get(suffix)


def pools_needing_prefix_enrichment(
    pool_documents: list[dict[str, Any]],
    *,
    program_code: str,
) -> dict[str, list[str]]:
    """Map pool requirementGroupId -> prefixes that should be merged into the explorer list."""
    needed: dict[str, list[str]] = {}
    for pool_document in pool_documents:
        prefixes = resolve_pool_allowed_prefixes(pool_document, program_code=program_code)
        if not prefixes:
            continue
        group_id = str(pool_document.get("requirementGroupId") or "")
        if group_id:
            needed[group_id] = prefixes
    return needed


def _course_matches_prefixes(course_number: str, prefixes: list[str]) -> bool:
    return any(
        course_number.startswith(prefix)
        or course_number.startswith(normalize_catalog_prefix(prefix))
        for prefix in prefixes
    )


def map_prefix_catalog_courses_to_pools(
    *,
    pool_prefixes: dict[str, list[str]],
    catalog_courses: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    for group_id, prefixes in pool_prefixes.items():
        mapped[group_id] = [
            course
            for course in catalog_courses
            if _course_matches_prefixes(str(course.get("courseNumber") or ""), prefixes)
        ]
    return mapped


def merge_course_references(*reference_lists: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for references in reference_lists:
        for reference in references or []:
            number = reference.get("courseNumber")
            if not number:
                continue
            normalized = str(number)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(reference)
    return merged


def _synthetic_refs_from_catalog_courses(
    catalog_courses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "courseNumber": course.get("courseNumber"),
            "titleHint": course.get("title") or course.get("titleHebrew"),
            "creditsHint": course.get("credits"),
        }
        for course in catalog_courses
        if course.get("courseNumber")
    ]


def _always_include_refs(pool_document: dict[str, Any], *, program_code: str) -> list[dict[str, Any]]:
    suffix = _pool_suffix(str(pool_document.get("requirementGroupId") or ""), program_code)
    rule = pool_document.get("ruleExpression") or {}
    numbers = list(ALWAYS_INCLUDE_NUMBERS_BY_SUFFIX.get(suffix, ()))
    for number in rule.get("alwaysIncludeCourseNumbers") or []:
        if number and str(number) not in numbers:
            numbers.append(str(number))
    return [{"courseNumber": number} for number in numbers]


def _course_list_source(
    *,
    explicit_count: int,
    included_count: int,
    prefix_count: int,
) -> str:
    if prefix_count and (explicit_count or included_count):
        return "vault_union"
    if prefix_count:
        return "prefix_catalog"
    if included_count:
        return "vault_union"
    if explicit_count:
        return "explicit"
    return "empty"


def _explorer_fallback_refs(pool_document: dict[str, Any], *, program_code: str) -> list[dict[str, Any]]:
    if pool_document.get("courseReferences"):
        return []
    suffix = _pool_suffix(str(pool_document.get("requirementGroupId") or ""), program_code)
    numbers = CHOOSE_N_CHAIN_FALLBACK_NUMBERS.get(suffix) or FOCUS_CHAIN_FALLBACK_NUMBERS.get(suffix, ())
    return [{"courseNumber": number} for number in numbers]


def enrich_pool_documents_for_explorer(
    pool_documents: list[dict[str, Any]],
    *,
    program_code: str,
    prefix_courses_by_pool: dict[str, list[dict[str, Any]]],
    courses_truncated: bool,
) -> list[dict[str, Any]]:
    pools_by_group_id = {
        str(document.get("requirementGroupId")): document
        for document in pool_documents
        if document.get("requirementGroupId")
    }

    enriched: list[dict[str, Any]] = []
    for pool_document in pool_documents:
        group_id = str(pool_document.get("requirementGroupId") or "")
        original_explicit_refs = list(pool_document.get("courseReferences") or [])
        explicit_refs = list(original_explicit_refs)
        used_focus_fallback = False
        if not explicit_refs:
            explicit_refs = _explorer_fallback_refs(pool_document, program_code=program_code)
            used_focus_fallback = bool(explicit_refs)

        included_refs: list[dict[str, Any]] = []
        included_suffix = resolve_included_pool_suffix(pool_document, program_code=program_code)
        if included_suffix:
            included_pool = pools_by_group_id.get(f"{program_code}:{included_suffix}")
            if included_pool:
                included_refs = list(included_pool.get("courseReferences") or [])

        prefix_refs = _synthetic_refs_from_catalog_courses(prefix_courses_by_pool.get(group_id, []))
        always_refs = _always_include_refs(pool_document, program_code=program_code)
        merged_refs = merge_course_references(explicit_refs, included_refs, prefix_refs, always_refs)

        if (
            not used_focus_fallback
            and merged_refs == original_explicit_refs
            and not prefix_refs
            and not included_refs
            and not always_refs
        ):
            enriched.append(pool_document)
            continue

        list_source = _course_list_source(
            explicit_count=len(explicit_refs),
            included_count=len(included_refs),
            prefix_count=len(prefix_refs),
        )
        enriched.append(
            {
                **pool_document,
                "courseReferences": merged_refs,
                "explorerCourseListSource": list_source,
                "explorerCoursesTruncated": courses_truncated and bool(prefix_refs),
            }
        )
    return enriched
