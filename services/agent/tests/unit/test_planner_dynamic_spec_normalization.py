"""Unit tests for planner dynamic spec normalization (Phase 20)."""

from __future__ import annotations

from app.agent.planner.dynamic_spec_policy import normalize_planner_dynamic_specs
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.config import Settings

_ON = Settings(AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=True, AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN=True)
_OFF = Settings(AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=False)


def _spec(**overrides) -> dict:
    base = {
        "spec_id": "spec_norm_001",
        "agent_name": "course_comparison_agent",
        "role": "comparison analyst",
        "objective": "Compare course options",
        "reasoning_pattern": "single_pass",
        "expected_output_schema_name": "dynamic_agent_output_v1",
        "shadow_only": True,
    }
    base.update(overrides)
    return base


def _plan(*subtasks: PlannerSubtask) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-norm",
        user_goal="Compare courses",
        execution_mode="single_capability",
        recommended_autonomy_level=4,
        primary_intent="course_question",
        subtasks=list(subtasks),
        decision_summary="test",
        confidence=0.8,
    )


def test_flag_off_strips_dynamic_agent_spec() -> None:
    plan = _plan(
        PlannerSubtask(
            id="st1",
            title="Analyze",
            kind="analyze",
            capability_name="dynamic_agent",
            objective="Analyze",
            dynamic_agent_spec=_spec(),
        )
    )
    updated, diagnostics = normalize_planner_dynamic_specs(planner_output=plan, settings=_OFF)
    assert updated.subtasks[0].dynamic_agent_spec is None
    assert diagnostics["status"] == "skipped"


def test_flag_on_validates_valid_spec() -> None:
    plan = _plan(
        PlannerSubtask(
            id="st1",
            title="Analyze",
            kind="analyze",
            capability_name="dynamic_agent",
            objective="Analyze",
            dynamic_agent_spec=_spec(),
        )
    )
    updated, diagnostics = normalize_planner_dynamic_specs(planner_output=plan, settings=_ON)
    assert updated.subtasks[0].dynamic_agent_spec is not None
    assert updated.subtasks[0].dynamic_agent_spec_status == "validated"
    assert diagnostics["specsValidated"] == 1


def test_invalid_spec_removed_from_subtask() -> None:
    plan = _plan(
        PlannerSubtask(
            id="st1",
            title="Analyze",
            kind="analyze",
            capability_name="dynamic_agent",
            objective="Analyze",
            dynamic_agent_spec=_spec(allowed_observations=["bad_observation"]),
        )
    )
    updated, diagnostics = normalize_planner_dynamic_specs(planner_output=plan, settings=_ON)
    assert updated.subtasks[0].dynamic_agent_spec is None
    assert updated.subtasks[0].dynamic_agent_spec_status == "rejected"
    assert diagnostics["specsRejected"] == 1


def test_rejection_diagnostics_emitted() -> None:
    _, diagnostics = normalize_planner_dynamic_specs(
        planner_output=_plan(
            PlannerSubtask(
                id="st1",
                title="Analyze",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Analyze",
                dynamic_agent_spec=_spec(shadow_only=False),
            )
        ),
        settings=_ON,
    )
    assert diagnostics["rejectionReasons"]


def test_valid_specs_preserve_deterministic_order() -> None:
    plan = _plan(
        PlannerSubtask(id="a", title="A", kind="analyze", capability_name="dynamic_agent", objective="A", dynamic_agent_spec=_spec(spec_id="spec_a")),
        PlannerSubtask(id="b", title="B", kind="analyze", capability_name="dynamic_agent", objective="B", dynamic_agent_spec=_spec(spec_id="spec_b")),
    )
    updated, _ = normalize_planner_dynamic_specs(planner_output=plan, settings=_ON)
    assert [st.id for st in updated.subtasks] == ["a", "b"]


def test_output_schema_remains_planner_output_compatible() -> None:
    updated, _ = normalize_planner_dynamic_specs(
        planner_output=_plan(
            PlannerSubtask(
                id="st1",
                title="Analyze",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Analyze",
                dynamic_agent_spec=_spec(),
            )
        ),
        settings=_ON,
    )
    assert isinstance(updated, PlannerOutput)


def test_no_raw_spec_stored_in_diagnostics() -> None:
    _, diagnostics = normalize_planner_dynamic_specs(
        planner_output=_plan(
            PlannerSubtask(
                id="st1",
                title="Analyze",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Analyze",
                dynamic_agent_spec=_spec(),
            )
        ),
        settings=_ON,
    )
    dumped = str(diagnostics)
    assert "allowed_blocks" not in dumped
    assert "context_contract" not in dumped
