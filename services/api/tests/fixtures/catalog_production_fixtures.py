"""Synthetic production-like catalog fixtures for API tests."""

from __future__ import annotations

from app.db.catalog_bootstrap import (
    ADVISORY_COUNTS_BY_PROGRAM,
    ADVISORY_RULE_ID,
    ALL_PROGRAMS,
    EXCLUDED_COURSE,
    HARD_REQUIREMENT_ID,
    KNOWN_COURSE,
    KNOWN_PROGRAM,
    TOTAL_ADVISORY_RULES,
    TOTAL_HARD_REQUIREMENTS,
    seed_minimal_catalog,
)

__all__ = [
    "ADVISORY_COUNTS_BY_PROGRAM",
    "ADVISORY_RULE_ID",
    "ALL_PROGRAMS",
    "EXCLUDED_COURSE",
    "HARD_REQUIREMENT_ID",
    "KNOWN_COURSE",
    "KNOWN_PROGRAM",
    "TOTAL_ADVISORY_RULES",
    "TOTAL_HARD_REQUIREMENTS",
    "seed_catalog_production_fixtures",
]


async def seed_catalog_production_fixtures(database) -> None:
    await seed_minimal_catalog(database)
