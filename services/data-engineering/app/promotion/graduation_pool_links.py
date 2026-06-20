"""Phase 15.1 — explicit course_pool → credit_bucket links for production promotion."""

from __future__ import annotations

# Pool requirementGroupId → linked credit-bucket requirementGroupId (DDS Phase 15.1 signoff).
GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET: dict[str, str] = {
    "009216-1-000:elective-ds-pool": "009216-1-000:elective-ds",
    "009216-1-000:elective-faculty-pool": "009216-1-000:elective-faculty",
}


def linked_credit_bucket_for_pool(pool_group_id: str) -> str | None:
    return GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET.get(pool_group_id)
