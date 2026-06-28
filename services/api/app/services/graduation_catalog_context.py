"""Load catalog documents for graduation progress with explorer-consistent pool enrichment."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.curriculum.pool_course_enrichment import (
    EXPLORER_PREFIX_QUERY_LIMIT,
    enrich_pool_documents_for_explorer,
    map_prefix_catalog_courses_to_pools,
    pools_needing_prefix_enrichment,
)
from app.repositories import catalog_repository


async def enrich_pool_documents_for_program(
    database: AsyncIOMotorDatabase,
    *,
    program_code: str,
    pool_documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match curriculum graph pool enrichment so progress and explorer agree."""
    pool_prefixes = pools_needing_prefix_enrichment(pool_documents, program_code=program_code)
    prefix_catalog_courses: list[dict[str, Any]] = []
    courses_truncated = False

    if pool_prefixes:
        unique_prefixes = sorted(
            {prefix for prefixes in pool_prefixes.values() for prefix in prefixes}
        )
        prefix_catalog_courses = await catalog_repository.list_courses_by_number_prefixes(
            database,
            unique_prefixes,
            limit=EXPLORER_PREFIX_QUERY_LIMIT,
        )
        courses_truncated = len(prefix_catalog_courses) >= EXPLORER_PREFIX_QUERY_LIMIT

    prefix_courses_by_pool = map_prefix_catalog_courses_to_pools(
        pool_prefixes=pool_prefixes,
        catalog_courses=prefix_catalog_courses,
    )
    return enrich_pool_documents_for_explorer(
        pool_documents,
        program_code=program_code,
        prefix_courses_by_pool=prefix_courses_by_pool,
        courses_truncated=courses_truncated,
    )
