"""Links credit buckets to course_pool eligibility rules (catalog semantics)."""

from __future__ import annotations

from typing import Any

# Pool suffix → credit-bucket suffix for explorer / progress linking.
EXPLORER_POOL_CREDIT_BUCKET_SUFFIX: dict[str, str] = {
    "elective-ds-pool": "elective-ds",
    "elective-faculty-pool": "elective-faculty",
    "ie-statistics-elective-chain": "elective-faculty",
    "ie-behavior-science-chain": "elective-faculty",
    "ie-focus-chain-game-theory": "elective-faculty",
    "ie-focus-chain-advanced-industry": "elective-faculty",
    "ie-focus-chain-operations-research": "elective-faculty",
    "ie-additional-faculty-electives": "elective-faculty",
    "is-behavior-science-chain": "elective-faculty",
    "is-focus-chain-performance": "elective-faculty",
    "is-focus-chain-ml": "elective-faculty",
    "is-focus-chain-game-theory": "elective-faculty",
    "is-additional-faculty-electives": "elective-faculty",
}

# Maps credit-bucket suffix (after programCode) to course_pool group suffix.
ENFORCED_BUCKET_POOL_SUFFIXES: dict[str, str] = {
    "elective-ds": "elective-ds-pool",
    "elective-faculty": "elective-faculty-pool",
    "enrichment": "enrichment-pool",
    "physical-education": "physical-education-pool",
}

# course_pool groups enforced for graduation eligibility in Phase 15.
ENFORCED_POOL_RULE_TYPES = frozenset({"course_pool"})

# Planning-only rule types — never affect graduation progress.
PLANNING_ONLY_RULE_TYPES = frozenset({"semester_matrix"})

# Track rules require profile track selection (Phase 15.4).
TRACK_RULE_TYPES = frozenset({"track_requirement"})


def bucket_group_id(program_code: str, bucket_suffix: str) -> str:
    return f"{program_code}:{bucket_suffix}"


def pool_group_id(program_code: str, pool_suffix: str) -> str:
    return f"{program_code}:{pool_suffix}"


def linked_pool_group_id(program_code: str, bucket_suffix: str) -> str | None:
    pool_suffix = ENFORCED_BUCKET_POOL_SUFFIXES.get(bucket_suffix)
    if not pool_suffix:
        return None
    return pool_group_id(program_code, pool_suffix)


def bucket_suffix_from_group_id(requirement_group_id: str, program_code: str) -> str:
    prefix = f"{program_code}:"
    if requirement_group_id.startswith(prefix):
        return requirement_group_id[len(prefix) :]
    return requirement_group_id


def index_pools_by_linked_bucket(
    pool_documents: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Phase 15.1 — map credit bucket requirementGroupId -> pool document."""
    indexed: dict[str, dict[str, Any]] = {}
    for document in pool_documents:
        linked_bucket_id = document.get("linkedCreditBucketId")
        if linked_bucket_id:
            indexed[str(linked_bucket_id)] = document
    return indexed


def credit_bucket_id_for_pool(
    *,
    program_code: str,
    pool_document: dict[str, Any],
) -> str | None:
    """Map a course_pool document to its linked credit-bucket requirementGroupId."""
    explicit = pool_document.get("linkedCreditBucketId")
    if explicit:
        return str(explicit)

    group_id = str(pool_document.get("requirementGroupId") or "")
    prefix = f"{program_code}:"
    if not group_id.startswith(prefix):
        return None

    suffix = group_id[len(prefix) :]
    explorer_bucket_suffix = EXPLORER_POOL_CREDIT_BUCKET_SUFFIX.get(suffix)
    if explorer_bucket_suffix:
        return bucket_group_id(program_code, explorer_bucket_suffix)

    if suffix.endswith("-pool"):
        bucket_suffix = suffix[: -len("-pool")]
        if bucket_suffix in ENFORCED_BUCKET_POOL_SUFFIXES:
            return bucket_group_id(program_code, bucket_suffix)
    return None


def resolve_pool_for_bucket(
    *,
    program_code: str,
    bucket_suffix: str,
    pools_by_group_id: dict[str, dict[str, Any]],
    pools_by_linked_bucket: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (pool_document, linked_pool_group_id, strict_pool_enforcement).

    Phase 15.1 explicit linkedCreditBucketId takes precedence over Phase 15.0
    naming-convention links.
    """
    bucket_group = bucket_group_id(program_code, bucket_suffix)

    explicit_pool = pools_by_linked_bucket.get(bucket_group)
    if explicit_pool is not None:
        pool_group = explicit_pool.get("requirementGroupId")
        return (
            explicit_pool,
            str(pool_group) if pool_group is not None else None,
            True,
        )

    conventional_group = linked_pool_group_id(program_code, bucket_suffix)
    if conventional_group:
        conventional_pool = pools_by_group_id.get(conventional_group)
        if conventional_pool and bucket_suffix in ENFORCED_BUCKET_POOL_SUFFIXES:
            return conventional_pool, conventional_group, True

    return None, conventional_group, False
