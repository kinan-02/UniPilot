"""Unit tests for the Phase 4 Capability Registry."""

from __future__ import annotations

import pytest

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import (
    CapabilityNotFoundError,
    CapabilityRegistry,
    DuplicateCapabilityError,
)
from app.agent.capabilities.schemas import CapabilityDescriptor

_REQUIRED_WORKFLOWS = {
    "graduation_progress_workflow",
    "course_question_workflow",
    "transcript_import_workflow",
    "semester_planning_workflow",
    "requirement_explanation_workflow",
    "general_academic_workflow",
}

_REQUIRED_SPECIALIST_AGENTS = {
    "task_understanding_agent",
    "planner_agent",
    "graduation_progress_agent",
    "course_catalog_agent",
    "semester_planning_agent",
    "transcript_import_agent",
    "requirement_explanation_agent",
    "general_academic_rag_agent",
    "validator_agent",
    "response_composer_agent",
}

_REQUIRED_INTERNAL_APIS = {
    "graduation_audit_internal_api",
    "semester_plan_options_internal_api",
    "course_requirement_contribution_internal_api",
}


def test_default_registry_builds_successfully() -> None:
    registry = build_default_capability_registry()
    assert isinstance(registry, CapabilityRegistry)
    assert len(registry.list_capabilities()) > 0


def test_required_workflow_capabilities_exist() -> None:
    registry = build_default_capability_registry()
    names = set(registry.names())
    assert _REQUIRED_WORKFLOWS.issubset(names)
    for name in _REQUIRED_WORKFLOWS:
        assert registry.require(name).type == "workflow"


def test_future_specialist_agent_descriptors_exist() -> None:
    registry = build_default_capability_registry()
    names = set(registry.names())
    assert _REQUIRED_SPECIALIST_AGENTS.issubset(names)
    for name in _REQUIRED_SPECIALIST_AGENTS:
        assert registry.require(name).type == "specialist_agent"


def test_internal_api_capabilities_exist() -> None:
    registry = build_default_capability_registry()
    names = set(registry.names())
    assert _REQUIRED_INTERNAL_APIS.issubset(names)
    for name in _REQUIRED_INTERNAL_APIS:
        assert registry.require(name).type == "internal_api"


def test_duplicate_names_are_rejected() -> None:
    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor(name="dup", type="tool", description="first")
    registry.register(descriptor)
    with pytest.raises(DuplicateCapabilityError):
        registry.register(CapabilityDescriptor(name="dup", type="tool", description="second"))


def test_duplicate_registration_allowed_with_overwrite() -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilityDescriptor(name="dup", type="tool", description="first"))
    registry.register(
        CapabilityDescriptor(name="dup", type="tool", description="second"), overwrite=True
    )
    assert registry.require("dup").description == "second"


def test_get_returns_none_for_unknown_capability() -> None:
    registry = build_default_capability_registry()
    assert registry.get("does_not_exist") is None


def test_require_raises_for_unknown_capability() -> None:
    registry = build_default_capability_registry()
    with pytest.raises(CapabilityNotFoundError):
        registry.require("does_not_exist")


def test_get_and_require_return_same_descriptor_for_known_capability() -> None:
    registry = build_default_capability_registry()
    assert registry.get("course_question_workflow") is registry.require("course_question_workflow")


def test_find_by_intent_returns_expected_capabilities() -> None:
    registry = build_default_capability_registry()
    matches = registry.find_by_intent("course_question")
    names = {capability.name for capability in matches}
    assert "course_question_workflow" in names
    assert "course_catalog_agent" in names


def test_find_by_intent_returns_empty_for_unknown_intent() -> None:
    registry = build_default_capability_registry()
    assert registry.find_by_intent("totally_unknown_intent") == []


def test_find_by_type_returns_expected_capabilities() -> None:
    registry = build_default_capability_registry()
    workflows = registry.find_by_type("workflow")
    names = {capability.name for capability in workflows}
    assert names == _REQUIRED_WORKFLOWS
    for capability in workflows:
        assert capability.type == "workflow"


def test_find_for_task_category_returns_expected_capabilities() -> None:
    registry = build_default_capability_registry()
    matches = registry.find_for_task_category("planning")
    names = {capability.name for capability in matches}
    assert "semester_planning_workflow" in names


def test_disabled_capabilities_are_filtered_out_by_find_enabled() -> None:
    registry = build_default_capability_registry()
    enabled_names = {capability.name for capability in registry.find_enabled()}
    disabled_names = {
        capability.name for capability in registry.list_capabilities() if not capability.enabled
    }
    assert disabled_names, "expected at least one disabled placeholder capability"
    assert enabled_names.isdisjoint(disabled_names)
    # The live Phase 3 agent and all 6 live workflows must be enabled.
    assert "task_understanding_agent" in enabled_names
    assert _REQUIRED_WORKFLOWS.issubset(enabled_names)


def test_write_sensitive_capabilities_are_proposal_only_not_direct_write() -> None:
    registry = build_default_capability_registry()
    write_sensitive = [
        capability
        for capability in registry.list_capabilities()
        if capability.permissions.can_create_action_proposals
        or capability.permissions.can_execute_writes
    ]
    assert write_sensitive, "expected at least one write-sensitive capability"
    for capability in write_sensitive:
        assert capability.permissions.write_scope == "proposal_only"
        assert capability.permissions.can_execute_writes is False


def test_no_capability_can_execute_direct_writes() -> None:
    """Only api's own confirm/reject routes may execute a write — no agent capability may."""
    registry = build_default_capability_registry()
    for capability in registry.list_capabilities():
        assert capability.permissions.write_scope != "direct_write"
        assert capability.permissions.can_execute_writes is False


def test_source_of_truth_ranks_are_assignable_and_comparable() -> None:
    registry = build_default_capability_registry()
    ranked = [
        capability.source_of_truth_rank
        for capability in registry.list_capabilities()
        if capability.source_of_truth_rank is not None
    ]
    # Phase 4 does not require every capability to declare a rank yet, but
    # the field itself must be usable (int | None) without validation errors.
    for rank in ranked:
        assert isinstance(rank, int)
