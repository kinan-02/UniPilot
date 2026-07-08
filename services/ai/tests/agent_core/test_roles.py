"""Unit tests for `app.agent_core.roles` (docs/agent/AGENT_VISION.md §6, §6.1, §6.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
