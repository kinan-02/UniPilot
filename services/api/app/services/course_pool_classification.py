"""Classify completed courses into credit buckets and course pools."""

from __future__ import annotations

from typing import Any

from app.services.course_reference_keys import (
    build_mandatory_course_number_keys,
    build_mandatory_equivalence_groups,
    is_mandatory_curriculum_course,
    mandatory_group_for_course,
)
from app.services.graduation_requirement_links import bucket_suffix_from_group_id

__all__ = [
    "build_mandatory_course_number_keys",
    "build_mandatory_equivalence_groups",
    "is_mandatory_curriculum_course",
    "mandatory_group_for_course",
    "resolve_claiming_pool",
    "is_explicit_catalog_pool",
    "pool_group_suffix",
]


def pool_group_suffix(pool_document: dict[str, Any], program_code: str) -> str:
    group_id = str(pool_document.get("requirementGroupId") or "")
    return bucket_suffix_from_group_id(group_id, program_code)


def is_explicit_catalog_pool(pool_document: dict[str, Any], program_code: str) -> bool:
    rule = pool_document.get("ruleExpression") or {}
    operator = rule.get("operator")
    if operator in {"choose_chain", "choose_n"}:
        return True

    suffix = pool_group_suffix(pool_document, program_code)
    return (
        "focus-chain" in suffix
        or "behavior-science" in suffix
        or "statistics-elective" in suffix
    )


def is_prefix_catch_all_pool(pool_document: dict[str, Any], program_code: str) -> bool:
    suffix = pool_group_suffix(pool_document, program_code)
    if "additional" in suffix:
        return True
    rule = pool_document.get("ruleExpression") or {}
    from app.services.graduation_progress_calculator import _pool_allowed_prefixes

    return rule.get("operator") == "min_credits" and bool(
        _pool_allowed_prefixes(pool_document, program_code=program_code)
    )


def pool_specificity_rank(pool_document: dict[str, Any], program_code: str) -> int:
    rule = pool_document.get("ruleExpression") or {}
    operator = rule.get("operator")
    suffix = pool_group_suffix(pool_document, program_code)

    if operator == "choose_chain":
        return 100
    if operator == "choose_n":
        return 90
    if "focus-chain" in suffix:
        return 80
    if "behavior-science" in suffix or "statistics-elective" in suffix:
        return 70
    if suffix in {"enrichment-pool", "physical-education-pool"}:
        return 60
    if is_prefix_catch_all_pool(pool_document, program_code):
        return 40
    if suffix.endswith("-pool"):
        return 30
    return 10


def is_course_claimed_by_explicit_sibling_pool(
    course_number: str,
    pool_document: dict[str, Any],
    sibling_pools: list[dict[str, Any]],
    *,
    program_code: str,
) -> bool:
    from app.services.graduation_progress_calculator import is_course_eligible_for_pool

    pool_group = str(pool_document.get("requirementGroupId") or "")
    return any(
        is_explicit_catalog_pool(sibling, program_code)
        and str(sibling.get("requirementGroupId") or "") != pool_group
        and is_course_eligible_for_pool(course_number, sibling, program_code=program_code)
        for sibling in sibling_pools
    )


def resolve_claiming_pool(
    course_number: str | None,
    pool_documents: list[dict[str, Any]],
    *,
    program_code: str,
    equivalence_groups: list[set[str]] | None = None,
) -> dict[str, Any] | None:
    """Pick the single most specific pool that claims this course number."""
    from app.services.graduation_progress_calculator import is_course_eligible_for_pool

    if not course_number or not pool_documents:
        return None

    matching = [
        pool_document
        for pool_document in pool_documents
        if is_course_eligible_for_pool(
            course_number,
            pool_document,
            program_code=program_code,
            equivalence_groups=equivalence_groups,
        )
    ]
    if not matching:
        return None

    explicit_matches = [
        pool_document
        for pool_document in matching
        if is_explicit_catalog_pool(pool_document, program_code)
    ]
    if explicit_matches:
        return max(
            explicit_matches,
            key=lambda pool_document: pool_specificity_rank(pool_document, program_code),
        )

    prefix_matches = [
        pool_document
        for pool_document in matching
        if is_prefix_catch_all_pool(pool_document, program_code)
    ]
    if prefix_matches:
        filtered = [
            pool_document
            for pool_document in prefix_matches
            if not is_course_claimed_by_explicit_sibling_pool(
                course_number,
                pool_document,
                matching,
                program_code=program_code,
            )
        ]
        candidates = filtered or prefix_matches
        return max(
            candidates,
            key=lambda pool_document: pool_specificity_rank(pool_document, program_code),
        )

    return max(
        matching,
        key=lambda pool_document: pool_specificity_rank(pool_document, program_code),
    )

