"""Unit tests for `app.agent.specialists.tools.tool_requests.validate_tool_requests` (Phase 13)."""

from __future__ import annotations

from app.agent.reasoning.schemas import ReasoningToolRequest
from app.agent.specialists.tools.registry import ObservationDescriptor, SpecialistObservationRegistry
from app.agent.specialists.tools.tool_requests import validate_tool_requests


def _registry() -> SpecialistObservationRegistry:
    registry = SpecialistObservationRegistry()
    registry.register(
        ObservationDescriptor(
            name="profile_summary",
            description="test",
            allowed_specialists=("graduation_progress_agent", "course_catalog_agent"),
            source="agent_context_pack",
        )
    )
    registry.register(
        ObservationDescriptor(
            name="completed_courses_summary",
            description="test",
            allowed_specialists=("graduation_progress_agent",),
            source="agent_context_pack",
        )
    )
    registry.register(
        ObservationDescriptor(
            name="course_catalog_summary",
            description="test",
            allowed_specialists=("course_catalog_agent",),
            source="agent_context_pack",
        )
    )
    return registry


def _Req(tool_name: str, purpose: str = "need it", arguments: dict | None = None) -> ReasoningToolRequest:
    return ReasoningToolRequest(tool_name=tool_name, purpose=purpose, arguments=arguments or {})


# ---------------------------------------------------------------------------
# 1. Known allowed observation is approved.
# ---------------------------------------------------------------------------


def test_known_allowed_observation_is_approved() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == ["profile_summary"]
    assert outcome.results[0].status == "approved"


# ---------------------------------------------------------------------------
# 2. Unknown observation rejected.
# ---------------------------------------------------------------------------


def test_unknown_observation_rejected() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="totally_unknown_observation")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "unavailable"
    assert "tool_request_unknown_observation:totally_unknown_observation" in outcome.warnings


# ---------------------------------------------------------------------------
# 3. Observation not allowed for specialist rejected.
# ---------------------------------------------------------------------------


def test_observation_not_allowed_for_specialist_rejected() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="course_catalog_summary")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "rejected"
    assert "tool_request_not_allowed_for_specialist:course_catalog_summary" in outcome.warnings


# ---------------------------------------------------------------------------
# 4. Duplicate observation rejected/deduped deterministically.
# ---------------------------------------------------------------------------


def test_duplicate_observation_within_round_is_rejected_keeping_first() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary"), _Req(tool_name="profile_summary")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == ["profile_summary"]
    assert outcome.results[0].status == "approved"
    assert outcome.results[1].status == "rejected"
    assert "tool_request_duplicate_observation:profile_summary" in outcome.warnings


def test_duplicate_of_already_present_observation_is_rejected() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary")],
        specialist_agent_name="graduation_progress_agent",
        already_present_observations=["profile_summary"],
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "rejected"


# ---------------------------------------------------------------------------
# 5. Write/side-effect observation rejected.
# ---------------------------------------------------------------------------


def test_unsafe_descriptor_is_rejected_even_if_registered_and_allowed() -> None:
    registry = _registry()
    registry.register(
        ObservationDescriptor(
            name="hostile_write_observation",
            description="test",
            allowed_specialists=("graduation_progress_agent",),
            source="agent_context_pack",
            read_only=False,
        )
    )

    outcome = validate_tool_requests(
        [_Req(tool_name="hostile_write_observation")],
        specialist_agent_name="graduation_progress_agent",
        registry=registry,
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "rejected"


# ---------------------------------------------------------------------------
# 6. Request with forbidden argument key rejected.
# ---------------------------------------------------------------------------


def test_forbidden_argument_key_rejected() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary", arguments={"raw_context": {"secret": "x"}})],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "rejected"
    assert "tool_request_forbidden_arguments:raw_context" in outcome.warnings


def test_nested_forbidden_argument_key_rejected() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary", arguments={"outer": {"chain_of_thought": "secret"}})],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.results[0].status == "rejected"
    assert "tool_request_forbidden_arguments:chain_of_thought" in outcome.warnings


# ---------------------------------------------------------------------------
# 7. Max requests per round enforced.
# ---------------------------------------------------------------------------


def test_max_requests_per_round_enforced() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary"), _Req(tool_name="completed_courses_summary")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=1,
    )

    assert outcome.approved_observation_names == ["profile_summary"]
    assert outcome.results[1].status == "rejected"
    assert "tool_request_budget_exceeded" in outcome.results[1].warnings
    assert "tool_request_budget_exceeded" in outcome.warnings


def test_zero_budget_rejects_every_request() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=0,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results[0].status == "rejected"


# ---------------------------------------------------------------------------
# 8. Empty purpose still handled safely.
# ---------------------------------------------------------------------------


def test_empty_purpose_is_handled_safely_and_still_approved() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary", purpose="")],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == ["profile_summary"]


# ---------------------------------------------------------------------------
# 9. Malformed request never raises.
# ---------------------------------------------------------------------------


def test_malformed_dict_request_never_raises() -> None:
    outcome = validate_tool_requests(
        [{"purpose": "no name field at all"}, {"tool_name": None}, "not_even_a_dict", 123],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results == []


def test_none_requests_never_raises() -> None:
    outcome = validate_tool_requests(
        None,
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == []
    assert outcome.results == []


def test_non_dict_arguments_never_raises() -> None:
    outcome = validate_tool_requests(
        [{"tool_name": "profile_summary", "arguments": "not_a_dict"}],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    assert outcome.approved_observation_names == ["profile_summary"]


# ---------------------------------------------------------------------------
# Warnings never carry raw argument values.
# ---------------------------------------------------------------------------


def test_warnings_never_carry_raw_argument_values() -> None:
    outcome = validate_tool_requests(
        [_Req(tool_name="profile_summary", arguments={"raw_context": "TOP_SECRET_VALUE_XYZ"})],
        specialist_agent_name="graduation_progress_agent",
        registry=_registry(),
        max_requests_per_round=4,
    )

    warnings_text = str(outcome.warnings)
    assert "TOP_SECRET_VALUE_XYZ" not in warnings_text
