"""Unit tests for `app.agent.specialists.tools.registry` (Phase 12)."""

from __future__ import annotations

import pytest

from app.agent.specialists.tools.registry import (
    SPECIALIST_ALLOWED_OBSERVATIONS,
    ObservationDescriptor,
    SpecialistObservationNotFoundError,
    SpecialistObservationRegistry,
    build_default_observation_registry,
)
from app.agent.specialists.tools.safety import is_observation_descriptor_safe

_REQUIRED_OBSERVATIONS = (
    "profile_summary",
    "completed_courses_summary",
    "graduation_audit_summary",
    "requirement_bucket_summary",
    "course_catalog_summary",
    "prerequisite_summary",
    "offering_summary",
    "requirement_contribution_summary",
    "wiki_snippet_summary",
    "conversation_assumption_summary",
)


# ---------------------------------------------------------------------------
# 1. Default registry contains required observations.
# ---------------------------------------------------------------------------


def test_default_registry_contains_required_observations() -> None:
    registry = build_default_observation_registry()

    for name in _REQUIRED_OBSERVATIONS:
        assert registry.has(name), name


def test_default_registry_contains_exactly_the_required_observations() -> None:
    registry = build_default_observation_registry()
    assert set(registry.list_names()) == set(_REQUIRED_OBSERVATIONS)


# ---------------------------------------------------------------------------
# 2/3/4. Per-specialist allowed observations are correct.
# ---------------------------------------------------------------------------


def test_graduation_progress_agent_allowed_observations() -> None:
    registry = build_default_observation_registry()

    allowed = registry.allowed_observations_for_specialist("graduation_progress_agent")

    assert set(allowed) == {
        "profile_summary",
        "completed_courses_summary",
        "graduation_audit_summary",
        "requirement_bucket_summary",
        "conversation_assumption_summary",
    }


def test_course_catalog_agent_allowed_observations() -> None:
    registry = build_default_observation_registry()

    allowed = registry.allowed_observations_for_specialist("course_catalog_agent")

    assert set(allowed) == {
        "profile_summary",
        "completed_courses_summary",
        "course_catalog_summary",
        "prerequisite_summary",
        "offering_summary",
        "requirement_contribution_summary",
        "wiki_snippet_summary",
        "conversation_assumption_summary",
    }


def test_requirement_explanation_agent_allowed_observations() -> None:
    registry = build_default_observation_registry()

    allowed = registry.allowed_observations_for_specialist("requirement_explanation_agent")

    assert set(allowed) == {
        "profile_summary",
        "requirement_bucket_summary",
        "course_catalog_summary",
        "requirement_contribution_summary",
        "wiki_snippet_summary",
        "conversation_assumption_summary",
    }


def test_unknown_specialist_has_no_allowed_observations() -> None:
    registry = build_default_observation_registry()
    assert registry.allowed_observations_for_specialist("not_a_real_specialist") == []


def test_spec_mapping_constant_matches_registry() -> None:
    registry = build_default_observation_registry()
    for specialist, expected in SPECIALIST_ALLOWED_OBSERVATIONS.items():
        assert set(registry.allowed_observations_for_specialist(specialist)) == set(expected)


# ---------------------------------------------------------------------------
# 5. Unknown observation raises a clear error.
# ---------------------------------------------------------------------------


def test_require_unknown_observation_raises_clear_error() -> None:
    registry = build_default_observation_registry()

    with pytest.raises(SpecialistObservationNotFoundError):
        registry.require("not_a_real_observation")


def test_get_unknown_observation_returns_none() -> None:
    registry = build_default_observation_registry()
    assert registry.get("not_a_real_observation") is None


def test_has_unknown_observation_is_false() -> None:
    registry = build_default_observation_registry()
    assert registry.has("not_a_real_observation") is False


# ---------------------------------------------------------------------------
# 6. Registry order is deterministic.
# ---------------------------------------------------------------------------


def test_registry_order_is_deterministic_and_matches_spec_order() -> None:
    registry = build_default_observation_registry()
    assert registry.list_names() == list(_REQUIRED_OBSERVATIONS)


def test_registry_order_is_stable_across_multiple_builds() -> None:
    first = build_default_observation_registry().list_names()
    second = build_default_observation_registry().list_names()
    assert first == second


def test_allowed_observations_for_specialist_preserves_registry_order() -> None:
    registry = build_default_observation_registry()
    allowed = registry.allowed_observations_for_specialist("course_catalog_agent")
    # Must be a sub-sequence of the full registry order, not caller/dict order.
    assert allowed == [name for name in registry.list_names() if name in set(allowed)]


# ---------------------------------------------------------------------------
# 7/8. Every observation is read-only with no side effects.
# ---------------------------------------------------------------------------


def test_every_default_observation_is_read_only() -> None:
    registry = build_default_observation_registry()
    for descriptor in registry.list_descriptors():
        assert descriptor.read_only is True, descriptor.name


def test_no_default_observation_has_side_effects() -> None:
    registry = build_default_observation_registry()
    for descriptor in registry.list_descriptors():
        assert descriptor.side_effect_level == "none", descriptor.name
        assert is_observation_descriptor_safe(descriptor) is True, descriptor.name


def test_descriptor_safety_helper_flags_unsafe_descriptor() -> None:
    unsafe = ObservationDescriptor(
        name="fake",
        description="fake",
        allowed_specialists=(),
        source="agent_context_pack",
        read_only=False,
    )
    assert is_observation_descriptor_safe(unsafe) is False


# ---------------------------------------------------------------------------
# Registration mechanics.
# ---------------------------------------------------------------------------


def test_register_duplicate_name_without_overwrite_raises() -> None:
    registry = SpecialistObservationRegistry()
    descriptor = ObservationDescriptor(
        name="profile_summary", description="x", allowed_specialists=(), source="agent_context_pack"
    )
    registry.register(descriptor)

    with pytest.raises(ValueError):
        registry.register(descriptor)


def test_register_duplicate_name_with_overwrite_succeeds() -> None:
    registry = SpecialistObservationRegistry()
    descriptor = ObservationDescriptor(
        name="profile_summary", description="x", allowed_specialists=(), source="agent_context_pack"
    )
    registry.register(descriptor)
    registry.register(descriptor, overwrite=True)

    assert registry.list_names() == ["profile_summary"]


def test_every_observation_name_maps_to_at_least_one_specialist() -> None:
    registry = build_default_observation_registry()
    for descriptor in registry.list_descriptors():
        assert descriptor.allowed_specialists, descriptor.name
