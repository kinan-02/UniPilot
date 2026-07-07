"""Unit tests for `app.agent.specialists.schemas`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.specialists.schemas import (
    SpecialistAgentInput,
    SpecialistAgentOutput,
    SpecialistToolObservation,
)


def test_specialist_agent_input_defaults() -> None:
    specialist_input = SpecialistAgentInput(
        subtask_id="s1", agent_name="graduation_progress_agent", objective="check progress", user_message="hi"
    )

    assert specialist_input.compiled_context == {}
    assert specialist_input.dependency_outputs == {}
    assert specialist_input.deterministic_observations == []
    assert specialist_input.success_criteria == []
    assert specialist_input.validation_requirements == []
    assert specialist_input.dry_run is True


def test_specialist_agent_input_rejects_unknown_agent_name() -> None:
    with pytest.raises(ValidationError):
        SpecialistAgentInput(
            subtask_id="s1", agent_name="not_a_real_agent", objective="x", user_message="x"  # type: ignore[arg-type]
        )


def test_specialist_tool_observation_defaults() -> None:
    observation = SpecialistToolObservation(name="tool1")
    assert observation.summary == {}
    assert observation.source is None
    assert observation.warnings == []


def test_specialist_agent_output_proposed_actions_always_forced_empty() -> None:
    output = SpecialistAgentOutput(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="s1",
        decision_summary="done",
        confidence=0.5,
        proposed_actions=[{"actionType": "save_semester_plan"}],
    )
    assert output.proposed_actions == []


def test_specialist_agent_output_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        SpecialistAgentOutput(
            status="completed",
            agent_name="graduation_progress_agent",
            subtask_id="s1",
            decision_summary="done",
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        SpecialistAgentOutput(
            status="completed",
            agent_name="graduation_progress_agent",
            subtask_id="s1",
            decision_summary="done",
            confidence=-0.1,
        )


def test_specialist_agent_output_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SpecialistAgentOutput(
            status="bogus_status",  # type: ignore[arg-type]
            agent_name="graduation_progress_agent",
            subtask_id="s1",
            decision_summary="done",
            confidence=0.5,
        )


def test_specialist_agent_output_has_no_forbidden_fields() -> None:
    field_names = set(SpecialistAgentOutput.model_fields)
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in field_names


def test_specialist_agent_input_has_no_forbidden_fields() -> None:
    field_names = set(SpecialistAgentInput.model_fields)
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in field_names


def test_specialist_agent_output_defaults() -> None:
    output = SpecialistAgentOutput(
        status="skipped",
        agent_name="course_catalog_agent",
        subtask_id="s2",
        decision_summary="skipped",
        confidence=0.0,
    )
    assert output.result == {}
    assert output.key_findings == []
    assert output.missing_context == []
    assert output.warnings == []
    assert output.validation_notes == []
    assert output.sources == []
    assert output.proposed_actions == []
