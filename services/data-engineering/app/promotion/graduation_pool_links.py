"""Phase 15.1 — explicit course_pool → credit_bucket links for production promotion."""

from __future__ import annotations

DDS_PROGRAM_CODES: tuple[str, ...] = (
    "009216-1-000",
    "009009-1-000",
    "009118-1-000",
)

_FACULTY_POOL_LINKS: dict[str, str] = {
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

_GENERAL_TECHNION_POOL_LINKS: dict[str, str] = {
    "enrichment-pool": "enrichment",
    "free-elective-pool": "free-elective",
    "physical-education-pool": "physical-education",
}


def _build_graduation_pool_links() -> dict[str, str]:
    links: dict[str, str] = {}
    for program_code in DDS_PROGRAM_CODES:
        for pool_suffix, bucket_suffix in {
            **_FACULTY_POOL_LINKS,
            **_GENERAL_TECHNION_POOL_LINKS,
        }.items():
            links[f"{program_code}:{pool_suffix}"] = f"{program_code}:{bucket_suffix}"
    return links


# Pool requirementGroupId → linked credit-bucket requirementGroupId (DDS Phase 15.1 signoff).
GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET: dict[str, str] = _build_graduation_pool_links()


def linked_credit_bucket_for_pool(pool_group_id: str) -> str | None:
    return GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET.get(pool_group_id)
