"""Source-of-truth trust hierarchy (Phase 4).

Documents which data source should win when two pieces of context disagree
(e.g. the LLM's interpretation vs. the deterministic graduation calculator).
Rank 1 is the most trusted. This module is descriptive only in Phase 4 —
nothing calls it yet; it exists for future validators / conflict resolution
(Phase 5+) to depend on rather than re-inventing an ad-hoc ordering.
"""

from __future__ import annotations

# Lower rank number = more trusted. Gaps are intentional (room to insert new
# sources later without renumbering everything).
SOURCE_OF_TRUTH_HIERARCHY: tuple[str, ...] = (
    "deterministic_api_business_rules",
    "deterministic_agent_repositories",
    "graduation_calculator_output",
    "official_catalog_rules",
    "course_offerings_database",
    "transcript_parser_review",
    "wiki_rag_sources",
    "conversation_memory",
    "llm_interpretation",
)

_RANK_BY_SOURCE: dict[str, int] = {
    source: rank for rank, source in enumerate(SOURCE_OF_TRUTH_HIERARCHY, start=1)
}

# One rank below the least-trusted named source, for anything not in the
# hierarchy — treated as least trustworthy rather than raising, since this
# module is meant to be a safe, permissive helper for future callers.
_UNKNOWN_SOURCE_RANK = len(SOURCE_OF_TRUTH_HIERARCHY) + 1


def get_source_of_truth_rank(source_name: str) -> int:
    """Return the trust rank for `source_name` (1 = most trusted).

    Unknown source names are treated as the least trustworthy rank rather
    than raising, so callers can compare against arbitrary/unlisted sources
    defensively.
    """
    return _RANK_BY_SOURCE.get(source_name, _UNKNOWN_SOURCE_RANK)


def compare_source_trust(a: str, b: str) -> int:
    """Return -1 if `a` is more trusted than `b`, 1 if less, 0 if equal."""
    rank_a = get_source_of_truth_rank(a)
    rank_b = get_source_of_truth_rank(b)
    if rank_a < rank_b:
        return -1
    if rank_a > rank_b:
        return 1
    return 0


def is_higher_trust(a: str, b: str) -> bool:
    """Return True when `a` is strictly more trusted than `b`."""
    return compare_source_trust(a, b) < 0
