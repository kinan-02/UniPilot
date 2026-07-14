"""Unit tests for `app.agent_core.roles` (docs/agent/AGENT_VISION.md §6, §6.1, §6.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_core.roles.catalog import render_specialist_catalog
from app.agent_core.roles.prompts import build_prompt_registry_with_roles
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.roles.schemas import RoleDefinition, RoleReasoningDefaults
from app.agent_core.tools.default_registry import build_default_tool_registry

_ALL_ROLES = {"retrieval", "interpretation", "calculation_validation", "simulation_planning", "composition"}


def test_roster_has_all_five_roles():
    roster = build_default_role_roster()
    assert set(roster) == _ALL_ROLES


def test_composition_role_has_zero_tool_grant():
    roster = build_default_role_roster()
    assert roster["composition"].tool_grant_ceiling == ()


def test_composition_role_validator_rejects_a_nonempty_tool_grant():
    with pytest.raises(ValidationError):
        RoleDefinition(
            name="composition",
            prompt_contract_name="composition_agent_v1",
            tool_grant_ceiling=("get_entity",),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="low", min_iterations=1, max_iterations=1, temperature=0.0
            ),
        )


def test_higher_level_composite_tools_are_actually_granted_to_the_roles_that_need_them():
    """Regression guard: all 8 composite tools (docs/agent/HIGHER_LEVEL_TOOLS.md)
    were built, tested, and registered in the default ToolRegistry, but the
    roster's own tool_grant_ceiling was never updated to actually grant any
    of them -- found via a live-eval run where retrieval/simulation_planning
    kept re-assembling multi-primitive chains by hand across several rounds
    instead of using the one-call composite that already existed for it."""
    roster = build_default_role_roster()
    assert set(roster["retrieval"].tool_grant_ceiling) >= {
        "get_course_profile",
        "get_policy_answer",
        "get_track_requirements",
    }
    assert "get_policy_answer" in roster["interpretation"].tool_grant_ceiling
    assert set(roster["simulation_planning"].tool_grant_ceiling) >= {
        "simulate_course_disruption",
        "check_eligibility",
        "compare_plans",
        "audit_graduation_progress",
        "find_requirement_substitutes",
    }


def test_every_role_tool_grant_is_a_subset_of_the_registered_tools():
    roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()
    tool_names = set(tool_registry.names())
    for role in roster.values():
        assert set(role.tool_grant_ceiling).issubset(tool_names)


def test_prompt_registry_with_roles_has_generic_plus_all_five_role_contracts():
    registry = build_prompt_registry_with_roles()
    names = set(registry.names())
    assert {"generic_reasoning_block_v1", "schema_repair_v1"}.issubset(names)
    for role in build_default_role_roster().values():
        assert role.prompt_contract_name in names


def test_every_role_prompt_contract_resolves_from_the_roster():
    registry = build_prompt_registry_with_roles()
    roster = build_default_role_roster()
    for role in roster.values():
        contract = registry.get(role.prompt_contract_name)
        assert contract.name == role.prompt_contract_name


def test_every_role_has_a_nonempty_routing_capability():
    """The Specialist Router's capability catalog is rendered from these, so a
    missing statement would silently hand the router a blank line for a real
    specialist."""
    roster = build_default_role_roster()
    for role in roster.values():
        assert role.routing_capability.strip(), f"{role.name} has no routing_capability"


def test_render_specialist_catalog_names_every_role_its_capability_and_tools():
    roster = build_default_role_roster()
    catalog = render_specialist_catalog(roster)
    # Every specialist name + its full routing_capability sentence is rendered
    # verbatim (roster-derived, so it can never drift from the definitions).
    for role in roster.values():
        assert role.name in catalog
        assert role.routing_capability in catalog
    # Tool-bearing roles surface their actual grants as evidence of what they
    # operate on; the tool-less composition role still appears.
    assert "get_entity" in catalog  # retrieval
    assert "apply_deterministic_rule" in catalog  # calculation_validation
    assert "interpret_text" in catalog  # interpretation
    assert "composition" in catalog


def test_render_specialist_catalog_marks_the_tool_less_composition_role():
    roster = build_default_role_roster()
    catalog = render_specialist_catalog(roster)
    # A role with an empty tool_grant_ceiling must render an explicit
    # "no tools" marker, never a dangling empty "Tools:" line.
    composition_line = next(line for line in catalog.splitlines() if line.startswith("- composition"))
    assert "no tools" in composition_line.lower()
