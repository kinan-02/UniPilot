"""Unit tests for planner dynamic spec policy (Phase 20)."""

from __future__ import annotations

from app.agent.dynamic_agents.block_library import COMPARISON_SYNTHESIS_BLOCK, CONTEXT_FILTER_BLOCK
from app.agent.dynamic_agents.schemas import DynamicAgentValidationPolicy
from app.agent.planner.dynamic_spec_policy import (
    normalize_planner_dynamic_specs,
    should_allow_dynamic_spec_for_subtask,
    validate_planner_emitted_agent_spec,
)
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.config import Settings

_ON = Settings(
    AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=True,
    AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN=True,
    AGENT_PLANNER_DYNAMIC_SPECS_MAX_PER_PLAN=3,
)


def _spec(**overrides) -> dict:
    base = {
        "spec_id": "spec_policy_001",
        "agent_name": "course_comparison_agent",
        "role": "comparison analyst",
        "objective": "Compare course options",
        "reasoning_pattern": "single_pass",
        "expected_output_schema_name": "dynamic_agent_output_v1",
        "shadow_only": True,
    }
    base.update(overrides)
    return base


def _subtask(**overrides) -> dict:
    base = {
        "id": "analyze_courses",
        "title": "Analyze courses",
        "kind": "analyze",
        "capability_name": "dynamic_agent",
        "objective": "Compare course options",
        "requires_user_confirmation": False,
    }
    base.update(overrides)
    return base


def test_valid_single_pass_spec_accepted() -> None:
    spec, errors = validate_planner_emitted_agent_spec(spec_payload=_spec(), settings=_ON)
    assert errors == []
    assert spec is not None


def test_valid_tool_observation_loop_spec_accepted() -> None:
    spec, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(
            reasoning_pattern="tool_observation_loop",
            allowed_observations=["course_catalog_summary"],
        ),
        settings=_ON,
    )
    assert errors == []
    assert spec is not None


def test_valid_compare_and_synthesize_spec_accepted() -> None:
    spec, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(
            reasoning_pattern="compare_and_synthesize",
            allowed_blocks=[CONTEXT_FILTER_BLOCK, COMPARISON_SYNTHESIS_BLOCK],
        ),
        settings=_ON,
    )
    assert errors == []
    assert spec is not None


def test_shadow_only_false_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(spec_payload=_spec(shadow_only=False), settings=_ON)
    assert "shadow_only_must_be_true" in errors


def test_allow_writes_true_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(validation_policy={"allow_writes": True}),
        settings=_ON,
    )
    assert any("allow_writes" in error for error in errors)


def test_allow_proposed_actions_true_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(validation_policy={"allow_proposed_actions": True}),
        settings=_ON,
    )
    assert any("allow_proposed_actions" in error for error in errors)


def test_unknown_observation_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(allowed_observations=["not_real_observation"]),
        settings=_ON,
    )
    assert any(error.startswith("unknown_observation:") for error in errors)


def test_unknown_block_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(allowed_blocks=["missing_block"]),
        settings=_ON,
    )
    assert any(error.startswith("unknown_block:") for error in errors)


def test_incompatible_block_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(
            reasoning_pattern="single_pass",
            allowed_blocks=[COMPARISON_SYNTHESIS_BLOCK],
        ),
        settings=_ON,
    )
    assert any(error.startswith("incompatible_block:") for error in errors)


def test_unknown_reasoning_pattern_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload=_spec(reasoning_pattern="reflect_and_revise"),
        settings=_ON,
    )
    assert any("reasoning_pattern_not_allowed" in error for error in errors)


def test_disallowed_risk_level_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(spec_payload=_spec(risk_level="high"), settings=_ON)
    assert any("risk_level_not_allowed" in error for error in errors)


def test_max_specs_per_plan_enforced() -> None:
    plan = PlannerOutput(
        status="completed",
        plan_id="plan-max",
        user_goal="Compare",
        execution_mode="single_capability",
        recommended_autonomy_level=4,
        primary_intent="course_question",
        subtasks=[
            PlannerSubtask(
                id=f"st{i}",
                title="Analyze",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Analyze",
                dynamic_agent_spec=_spec(spec_id=f"spec_{i}"),
            )
            for i in range(4)
        ],
        decision_summary="test",
        confidence=0.8,
    )
    updated, diagnostics = normalize_planner_dynamic_specs(planner_output=plan, settings=_ON)
    assert diagnostics["specsValidated"] == 3
    assert diagnostics["specsRejected"] == 1
    assert sum(1 for st in updated.subtasks if st.dynamic_agent_spec is not None) == 3


def test_write_proposal_subtask_rejected() -> None:
    assert should_allow_dynamic_spec_for_subtask(
        subtask=_subtask(kind="propose_action"),
        settings=_ON,
    ) is False


def test_generated_code_field_rejected() -> None:
    _, errors = validate_planner_emitted_agent_spec(
        spec_payload={**_spec(), "python_code": "print('bad')"},
        settings=_ON,
    )
    assert any("generated_code_field" in error for error in errors)


def test_malformed_spec_never_crashes() -> None:
    spec, errors = validate_planner_emitted_agent_spec(spec_payload={"spec_id": 1}, settings=_ON)
    assert spec is None
    assert errors
