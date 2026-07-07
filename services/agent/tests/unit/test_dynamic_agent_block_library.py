"""Unit tests for the dynamic agent block library (Phase 15)."""

from __future__ import annotations

import pytest

from app.agent.dynamic_agents.block_library import (
    CLARIFICATION_NEED_CHECK_BLOCK,
    COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    COMPARISON_SYNTHESIS_BLOCK,
    CONTEXT_FILTER_BLOCK,
    OUTPUT_SCHEMA_VALIDATION_BLOCK,
    SAFETY_VALIDATION_BLOCK,
    SINGLE_PASS_REASONING_BLOCK,
    TOOL_OBSERVATION_LOOP_BLOCK,
    build_default_block_library,
)


_REQUIRED_BLOCKS = (
    CONTEXT_FILTER_BLOCK,
    SINGLE_PASS_REASONING_BLOCK,
    TOOL_OBSERVATION_LOOP_BLOCK,
    OUTPUT_SCHEMA_VALIDATION_BLOCK,
    SAFETY_VALIDATION_BLOCK,
    COMPARISON_SYNTHESIS_BLOCK,
    COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    CLARIFICATION_NEED_CHECK_BLOCK,
)


def test_default_library_contains_required_blocks() -> None:
    library = build_default_block_library()
    for name in _REQUIRED_BLOCKS:
        assert library.has(name), name


def test_block_order_deterministic() -> None:
    first = build_default_block_library().list_names()
    second = build_default_block_library().list_names()
    assert first == second


def test_every_block_is_read_only() -> None:
    for block in build_default_block_library().list_blocks():
        assert block.read_only is True, block.name


def test_every_block_has_side_effect_level_none() -> None:
    for block in build_default_block_library().list_blocks():
        assert block.side_effect_level == "none", block.name


def test_unknown_block_lookup_fails_clearly() -> None:
    library = build_default_block_library()
    assert library.get("missing_block") is None
    with pytest.raises(KeyError, match="unknown_block"):
        library.require("missing_block")


def test_compatibility_lookup_works_by_reasoning_pattern() -> None:
    library = build_default_block_library()
    compare_blocks = library.blocks_for_pattern("compare_and_synthesize")
    assert any(block.name == COMPARISON_SYNTHESIS_BLOCK for block in compare_blocks)


def test_no_write_or_proposal_blocks_exist() -> None:
    for block in build_default_block_library().list_blocks():
        assert block.side_effect_level not in {"write", "proposal"}, block.name
