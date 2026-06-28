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
) -> dict[str, list[dict[str, Any]]]:
    """Phase 15.1 — map credit bucket requirementGroupId -> linked pool documents."""
    indexed: dict[str, list[dict[str, Any]]] = {}
    for document in pool_documents:
        linked_bucket_id = document.get("linkedCreditBucketId")
        if linked_bucket_id:
            key = str(linked_bucket_id)
            indexed.setdefault(key, []).append(document)
    return indexed


def collect_eligibility_pools_for_bucket(
    *,
    program_code: str,
    bucket_suffix: str,
    pools_by_group_id: dict[str, dict[str, Any]],
    pools_by_linked_bucket: dict[str, list[dict[str, Any]]],
    pool_documents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Return (eligibility_pools, primary_linked_pool_group_id, strict_pool_enforcement).

    Shared credit buckets (especially elective-faculty) may have many linked pool
    documents (focus chains, behavior chains, prefix pool). Eligibility is the
    union of all applicable pools, not a single winning document.
    """
    bucket_group = bucket_group_id(program_code, bucket_suffix)
    pools: list[dict[str, Any]] = []
    seen_group_ids: set[str] = set()

    def add_pool(document: dict[str, Any] | None) -> None:
        if not document:
            return
        group_id = str(document.get("requirementGroupId") or "")
        if not group_id or group_id in seen_group_ids:
            return
        seen_group_ids.add(group_id)
        pools.append(document)

    conventional_group = linked_pool_group_id(program_code, bucket_suffix)
    if conventional_group and bucket_suffix in ENFORCED_BUCKET_POOL_SUFFIXES:
        add_pool(pools_by_group_id.get(conventional_group))

    for document in pools_by_linked_bucket.get(bucket_group, []):
        add_pool(document)

    program_prefix = f"{program_code}:"
    for document in pool_documents:
        group_id = str(document.get("requirementGroupId") or "")
        if not group_id.startswith(program_prefix):
            continue
        if document.get("linkedCreditBucketId"):
            continue
        mapped_bucket = credit_bucket_id_for_pool(
            program_code=program_code,
            pool_document=document,
        )
        if mapped_bucket == bucket_group:
            add_pool(document)

    explicit_pools = pools_by_linked_bucket.get(bucket_group, [])
    if explicit_pools:
        primary_group = str(explicit_pools[0].get("requirementGroupId") or "") or None
    elif conventional_group and any(
        str(pool.get("requirementGroupId") or "") == conventional_group for pool in pools
    ):
        primary_group = conventional_group
    elif pools:
        primary_group = str(pools[0].get("requirementGroupId") or "") or None
    else:
        primary_group = conventional_group

    strict = bool(pools) and (
        bucket_suffix in ENFORCED_BUCKET_POOL_SUFFIXES
        or bool(explicit_pools)
    )
    return pools, primary_group, strict


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
    pools_by_linked_bucket: dict[str, list[dict[str, Any]]],
    pool_documents: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (primary_pool_document, linked_pool_group_id, strict_pool_enforcement).

    The primary pool is used for API metadata; eligibility may include additional
    linked/explorer pools via ``collect_eligibility_pools_for_bucket``.
    """
    pools, primary_group, strict = collect_eligibility_pools_for_bucket(
        program_code=program_code,
        bucket_suffix=bucket_suffix,
        pools_by_group_id=pools_by_group_id,
        pools_by_linked_bucket=pools_by_linked_bucket,
        pool_documents=pool_documents or [],
    )
    if not pools:
        return None, primary_group, strict

    primary_document = None
    if primary_group:
        primary_document = next(
            (
                document
                for document in pools
                if str(document.get("requirementGroupId") or "") == primary_group
            ),
            None,
        )
    if primary_document is None:
        primary_document = pools[0]
        primary_group = str(primary_document.get("requirementGroupId") or "") or primary_group

    return primary_document, primary_group, strict
