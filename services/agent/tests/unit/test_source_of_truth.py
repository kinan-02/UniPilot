"""Unit tests for the Phase 4 source-of-truth trust hierarchy."""

from __future__ import annotations

from app.agent.capabilities.source_of_truth import (
    SOURCE_OF_TRUTH_HIERARCHY,
    compare_source_trust,
    get_source_of_truth_rank,
    is_higher_trust,
)


def test_hierarchy_has_no_duplicate_sources() -> None:
    assert len(SOURCE_OF_TRUTH_HIERARCHY) == len(set(SOURCE_OF_TRUTH_HIERARCHY))


def test_hierarchy_places_deterministic_business_rules_first() -> None:
    assert SOURCE_OF_TRUTH_HIERARCHY[0] == "deterministic_api_business_rules"


def test_hierarchy_places_llm_interpretation_last() -> None:
    assert SOURCE_OF_TRUTH_HIERARCHY[-1] == "llm_interpretation"


def test_ranks_are_stable_and_monotonically_increasing() -> None:
    ranks = [get_source_of_truth_rank(source) for source in SOURCE_OF_TRUTH_HIERARCHY]
    assert ranks == sorted(ranks)
    assert len(ranks) == len(set(ranks))
    # Repeated calls must return the same rank (deterministic, no hidden state).
    for source in SOURCE_OF_TRUTH_HIERARCHY:
        assert get_source_of_truth_rank(source) == get_source_of_truth_rank(source)


def test_unknown_source_ranks_below_every_known_source() -> None:
    unknown_rank = get_source_of_truth_rank("some_source_not_in_the_hierarchy")
    for source in SOURCE_OF_TRUTH_HIERARCHY:
        assert unknown_rank > get_source_of_truth_rank(source)


def test_compare_source_trust_returns_expected_sign() -> None:
    assert compare_source_trust("deterministic_api_business_rules", "llm_interpretation") < 0
    assert compare_source_trust("llm_interpretation", "deterministic_api_business_rules") > 0
    assert compare_source_trust("wiki_rag_sources", "wiki_rag_sources") == 0


def test_is_higher_trust() -> None:
    assert is_higher_trust("graduation_calculator_output", "llm_interpretation") is True
    assert is_higher_trust("llm_interpretation", "graduation_calculator_output") is False
    assert is_higher_trust("conversation_memory", "conversation_memory") is False


def test_is_higher_trust_matches_compare_source_trust() -> None:
    for a in SOURCE_OF_TRUTH_HIERARCHY:
        for b in SOURCE_OF_TRUTH_HIERARCHY:
            assert is_higher_trust(a, b) == (compare_source_trust(a, b) < 0)
