"""Unit tests for `app.agent.specialists.tools.tool_loop_schemas` (Phase 13)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.specialists.schemas import SpecialistAgentOutput
from app.agent.specialists.tools.tool_loop_schemas import (
    SpecialistObservationToolRequest,
    SpecialistObservationToolResult,
    SpecialistToolLoopDiagnostics,
)

_FORBIDDEN_FIELD_NAMES = ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts")


def test_tool_request_defaults() -> None:
    request = SpecialistObservationToolRequest(observation_name="profile_summary", purpose="need it")

    assert request.arguments == {}


def test_tool_request_requires_observation_name() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservationToolRequest(purpose="need it")  # type: ignore[call-arg]


def test_tool_request_purpose_defaults_empty() -> None:
    request = SpecialistObservationToolRequest(observation_name="profile_summary")
    assert request.purpose == ""


def test_tool_result_defaults() -> None:
    result = SpecialistObservationToolResult(observation_name="profile_summary", status="approved")

    assert result.summary == {}
    assert result.warnings == []


def test_tool_result_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservationToolResult(observation_name="x", status="bogus")  # type: ignore[arg-type]


@pytest.mark.parametrize("status", ["approved", "rejected", "unavailable", "failed"])
def test_tool_result_accepts_every_valid_status(status: str) -> None:
    result = SpecialistObservationToolResult(observation_name="x", status=status)  # type: ignore[arg-type]
    assert result.status == status


def test_tool_loop_diagnostics_defaults() -> None:
    diagnostics = SpecialistToolLoopDiagnostics(status="skipped")

    assert diagnostics.rounds_used == 0
    assert diagnostics.requested_observations == []
    assert diagnostics.approved_observations == []
    assert diagnostics.rejected_observations == []
    assert diagnostics.missing_observations == []
    assert diagnostics.warnings == []


@pytest.mark.parametrize(
    "status", ["completed", "completed_with_tools", "skipped", "failed", "budget_exceeded"]
)
def test_tool_loop_diagnostics_accepts_every_valid_status(status: str) -> None:
    diagnostics = SpecialistToolLoopDiagnostics(status=status)  # type: ignore[arg-type]
    assert diagnostics.status == status


def test_tool_loop_diagnostics_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SpecialistToolLoopDiagnostics(status="bogus")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "model", [SpecialistObservationToolRequest, SpecialistObservationToolResult, SpecialistToolLoopDiagnostics]
)
def test_tool_loop_models_have_no_forbidden_fields(model) -> None:
    field_names = set(model.model_fields)
    for forbidden in _FORBIDDEN_FIELD_NAMES:
        assert forbidden not in field_names


def test_specialist_agent_output_gained_optional_tool_loop_diagnostics_field() -> None:
    """Phase 13 additive change: `SpecialistAgentOutput` gains
    `tool_loop_diagnostics` (default `None`) -- must not break the existing
    Phase 10/11/12 construction shape."""
    output = SpecialistAgentOutput(
        status="completed", agent_name="graduation_progress_agent", subtask_id="s1",
        decision_summary="done", confidence=0.5,
    )
    assert output.tool_loop_diagnostics is None


def test_specialist_agent_output_can_carry_tool_loop_diagnostics() -> None:
    diagnostics = SpecialistToolLoopDiagnostics(status="completed_with_tools", rounds_used=1)
    output = SpecialistAgentOutput(
        status="completed", agent_name="graduation_progress_agent", subtask_id="s1",
        decision_summary="done", confidence=0.5, tool_loop_diagnostics=diagnostics,
    )
    assert output.tool_loop_diagnostics is diagnostics


def test_specialist_agent_output_never_exposes_chain_of_thought_via_tool_loop_diagnostics() -> None:
    diagnostics = SpecialistToolLoopDiagnostics(
        status="completed_with_tools", rounds_used=1, requested_observations=["profile_summary"]
    )
    output = SpecialistAgentOutput(
        status="completed", agent_name="graduation_progress_agent", subtask_id="s1",
        decision_summary="done", confidence=0.5, tool_loop_diagnostics=diagnostics,
    )
    dumped_text = str(output.model_dump())
    for forbidden in _FORBIDDEN_FIELD_NAMES:
        assert forbidden not in dumped_text
