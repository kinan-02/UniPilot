"""Unit tests for `AgentBuilder` (Phase 15)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.dynamic_agents.block_library import (
    CONTEXT_FILTER_BLOCK,
    OUTPUT_SCHEMA_VALIDATION_BLOCK,
    SINGLE_PASS_REASONING_BLOCK,
    TOOL_OBSERVATION_LOOP_BLOCK,
)
from app.agent.dynamic_agents.builder import AgentBuilder
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentBudget
from app.agent.dynamic_agents.spec_validation import AgentSpecValidationError


def _valid_spec(**overrides) -> AgentSpec:
    defaults = dict(
        spec_id="spec_001",
        agent_name="test_dynamic_agent",
        role="analyst",
        objective="Analyze plans",
        reasoning_pattern="single_pass",
        expected_output_schema_name="dynamic_agent_output_v1",
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def test_builder_assembles_valid_single_pass_agent() -> None:
    instance = AgentBuilder().build(_valid_spec())
    names = [block.name for block in instance.blocks]
    assert CONTEXT_FILTER_BLOCK in names
    assert SINGLE_PASS_REASONING_BLOCK in names
    assert OUTPUT_SCHEMA_VALIDATION_BLOCK in names


def test_builder_assembles_valid_tool_observation_loop_agent() -> None:
    instance = AgentBuilder().build(
        _valid_spec(
            reasoning_pattern="tool_observation_loop",
            allowed_observations=["course_catalog_summary"],
            budget=DynamicAgentBudget(max_tool_rounds=1),
        )
    )
    names = [block.name for block in instance.blocks]
    assert TOOL_OBSERVATION_LOOP_BLOCK in names


def test_builder_rejects_invalid_spec() -> None:
    with pytest.raises(AgentSpecValidationError):
        AgentBuilder().build(_valid_spec(shadow_only=False))


def test_builder_does_not_execute_during_build() -> None:
    with patch("app.agent.dynamic_agents.runtime.ReasoningBlock") as mock_block:
        AgentBuilder().build(_valid_spec())
        mock_block.assert_not_called()


def test_builder_does_not_call_llm() -> None:
    with patch("app.agent.dynamic_agents.runtime.ChatLLMAdapter") as mock_adapter:
        AgentBuilder().build(_valid_spec())
        mock_adapter.assert_not_called()


def test_builder_does_not_generate_code() -> None:
    instance = AgentBuilder().build(_valid_spec())
    assert all(hasattr(block, "name") for block in instance.blocks)


def test_builder_preserves_block_order() -> None:
    spec = _valid_spec(
        allowed_blocks=[
            CONTEXT_FILTER_BLOCK,
            SINGLE_PASS_REASONING_BLOCK,
            OUTPUT_SCHEMA_VALIDATION_BLOCK,
        ]
    )
    instance = AgentBuilder().build(spec)
    assert [block.name for block in instance.blocks] == spec.allowed_blocks


def test_builder_output_is_deterministic() -> None:
    builder = AgentBuilder()
    first = [block.name for block in builder.build(_valid_spec()).blocks]
    second = [block.name for block in builder.build(_valid_spec()).blocks]
    assert first == second
