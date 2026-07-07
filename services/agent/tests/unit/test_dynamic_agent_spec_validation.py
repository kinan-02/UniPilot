"""Unit tests for dynamic agent spec validation (Phase 15)."""

from __future__ import annotations

from app.agent.dynamic_agents.block_library import (
    CONTEXT_FILTER_BLOCK,
    OUTPUT_SCHEMA_VALIDATION_BLOCK,
    SINGLE_PASS_REASONING_BLOCK,
)
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentBudget, DynamicAgentValidationPolicy
from app.agent.dynamic_agents.spec_validation import validate_agent_spec


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


def test_valid_single_pass_spec_passes() -> None:
    assert validate_agent_spec(_valid_spec()) == []


def test_valid_tool_observation_loop_spec_passes() -> None:
    spec = _valid_spec(
        reasoning_pattern="tool_observation_loop",
        allowed_observations=["course_catalog_summary"],
        budget=DynamicAgentBudget(max_tool_rounds=1),
    )
    assert validate_agent_spec(spec) == []


def test_shadow_only_false_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(shadow_only=False))
    assert "shadow_only_must_be_true" in errors


def test_allow_writes_true_rejected() -> None:
    policy = DynamicAgentValidationPolicy(allow_writes=True)
    errors = validate_agent_spec(_valid_spec(validation_policy=policy))
    assert "validation_policy_allow_writes_forbidden" in errors


def test_allow_proposed_actions_true_rejected() -> None:
    policy = DynamicAgentValidationPolicy(allow_proposed_actions=True)
    errors = validate_agent_spec(_valid_spec(validation_policy=policy))
    assert "validation_policy_allow_proposed_actions_forbidden" in errors


def test_unknown_block_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(allowed_blocks=["missing_block"]))
    assert any(error.startswith("unknown_block:") for error in errors)


def test_incompatible_block_rejected() -> None:
    errors = validate_agent_spec(
        _valid_spec(
            reasoning_pattern="single_pass",
            allowed_blocks=[CONTEXT_FILTER_BLOCK, "comparison_synthesis_block"],
        )
    )
    assert any(error.startswith("incompatible_block:") for error in errors)


def test_unknown_observation_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(allowed_observations=["not_a_real_observation"]))
    assert any(error.startswith("unknown_observation:") for error in errors)


def test_missing_objective_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(objective="   "))
    assert "objective_required" in errors


def test_missing_output_schema_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(expected_output_schema_name=""))
    assert "expected_output_schema_name_required" in errors


def test_budget_above_hard_caps_rejected() -> None:
    errors = validate_agent_spec(_valid_spec(budget=DynamicAgentBudget(max_reasoning_calls=99)))
    assert any(error.startswith("budget_max_reasoning_calls_exceeds_cap:") for error in errors)


def test_forbidden_context_key_rejected() -> None:
    from app.agent.dynamic_agents.schemas import DynamicAgentContextContract

    contract = DynamicAgentContextContract(
        allowed_context_sections=["profile_summary"],
        forbidden_context_keys=["profile_summary"],
    )
    errors = validate_agent_spec(_valid_spec(context_contract=contract))
    assert any(error.startswith("forbidden_context_key_requested:") for error in errors)


def test_generated_code_looking_field_rejected() -> None:
    errors = validate_agent_spec(
        {
            "spec_id": "x",
            "agent_name": "a",
            "role": "r",
            "objective": "o",
            "reasoning_pattern": "single_pass",
            "expected_output_schema_name": "dynamic_agent_output_v1",
            "scratchpad": "notes",
        }
    )
    assert any("forbidden_spec_field" in error for error in errors)


def test_malformed_spec_never_crashes() -> None:
    errors = validate_agent_spec({"spec_id": 123})
    assert errors
