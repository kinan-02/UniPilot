"""Unit tests for dynamic agent schemas (Phase 15)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.dynamic_agents.schemas import (
    AgentSpec,
    BlockDescriptor,
    DynamicAgentRunOutput,
    TaskBrief,
)


def _valid_spec(**overrides):
    defaults = dict(
        spec_id="spec_001",
        agent_name="test_dynamic_agent",
        role="comparison analyst",
        objective="Compare two semester plans",
        reasoning_pattern="single_pass",
        expected_output_schema_name="dynamic_agent_output_v1",
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def test_valid_agent_spec_parses() -> None:
    spec = _valid_spec()
    assert spec.shadow_only is True
    assert spec.validation_policy.allow_writes is False
    assert spec.validation_policy.allow_proposed_actions is False


def test_valid_task_brief_parses() -> None:
    brief = TaskBrief(
        brief_id="brief_001",
        objective="Compare plans",
        user_goal="Which plan is lighter?",
    )
    assert brief.brief_id == "brief_001"


def test_valid_block_descriptor_parses() -> None:
    block = BlockDescriptor(
        name="context_filter_block",
        block_type="context_filter",
        description="filter",
        when_to_use="always",
    )
    assert block.read_only is True
    assert block.side_effect_level == "none"


def test_budget_defaults_are_safe() -> None:
    spec = _valid_spec()
    assert spec.budget.max_reasoning_calls == 1
    assert spec.budget.max_tool_rounds == 0
    assert spec.budget.max_observations == 6


def test_validation_policy_defaults_forbid_writes_and_proposals() -> None:
    spec = _valid_spec()
    assert spec.validation_policy.allow_writes is False
    assert spec.validation_policy.allow_proposed_actions is False


def test_forbidden_chain_of_thought_fields_are_absent() -> None:
    with pytest.raises(ValidationError):
        AgentSpec.model_validate(
            {
                "spec_id": "x",
                "agent_name": "a",
                "role": "r",
                "objective": "o",
                "reasoning_pattern": "single_pass",
                "expected_output_schema_name": "dynamic_agent_output_v1",
                "chain_of_thought": "secret",
            }
        )


def test_proposed_actions_default_empty() -> None:
    output = DynamicAgentRunOutput(
        status="completed",
        spec_id="spec_001",
        agent_name="agent",
        decision_summary="done",
        confidence=0.5,
        proposed_actions=[{"type": "write"}],
    )
    assert output.proposed_actions == []
