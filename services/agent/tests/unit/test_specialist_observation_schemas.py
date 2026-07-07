"""Unit tests for `app.agent.specialists.tools.schemas` (Phase 12)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.specialists.schemas import SpecialistToolObservation
from app.agent.specialists.tools.schemas import (
    SpecialistObservation,
    SpecialistObservationBundle,
    SpecialistObservationRequest,
)


def test_specialist_observation_defaults() -> None:
    observation = SpecialistObservation(name="profile_summary", source="agent_context_pack")

    assert observation.status == "available"
    assert observation.summary == {}
    assert observation.warnings == []
    assert observation.confidence == 1.0


def test_specialist_observation_requires_source() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservation(name="profile_summary")  # type: ignore[call-arg]


def test_specialist_observation_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservation(name="x", source="agent_context_pack", status="bogus")  # type: ignore[arg-type]


def test_specialist_observation_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservation(name="x", source="bogus_source")  # type: ignore[arg-type]


def test_specialist_observation_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        SpecialistObservation(name="x", source="agent_context_pack", confidence=1.5)
    with pytest.raises(ValidationError):
        SpecialistObservation(name="x", source="agent_context_pack", confidence=-0.1)


def test_specialist_observation_request_defaults() -> None:
    request = SpecialistObservationRequest(
        specialist_agent_name="graduation_progress_agent",
        subtask_id="s1",
        objective="check progress",
        user_message="hi",
    )

    assert request.compiled_context == {}
    assert request.agent_context_pack_summary == {}
    assert request.dependency_outputs == {}
    assert request.allowed_observations == []
    assert request.max_observations == 8


def test_specialist_observation_bundle_defaults() -> None:
    bundle = SpecialistObservationBundle(specialist_agent_name="graduation_progress_agent", subtask_id="s1")

    assert bundle.observations == []
    assert bundle.warnings == []
    assert bundle.omitted_observations == []


@pytest.mark.parametrize(
    "model", [SpecialistObservation, SpecialistObservationRequest, SpecialistObservationBundle]
)
def test_specialist_observation_models_have_no_forbidden_fields(model) -> None:
    field_names = set(model.model_fields)
    for forbidden in (
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "raw_context",
        "raw_prompt",
        "proposed_actions",
    ):
        assert forbidden not in field_names


def test_specialist_tool_observation_gained_status_field_with_safe_default() -> None:
    """Phase 12 additive change: `SpecialistToolObservation` gains a
    `status` field (default `"available"`) -- must not break the Phase 10
    `SpecialistToolObservation(name="tool1")` construction shape."""
    observation = SpecialistToolObservation(name="tool1")

    assert observation.status == "available"
    assert observation.summary == {}
    assert observation.source is None
    assert observation.warnings == []


def test_specialist_tool_observation_accepts_missing_status() -> None:
    observation = SpecialistToolObservation(name="graduation_audit_summary", status="missing")
    assert observation.status == "missing"
