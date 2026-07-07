"""Deterministic AgentSpec validation (Phase 15).

Validates specs before `AgentBuilder` assembles a `DynamicAgentInstance`.
Never calls an LLM and never executes anything.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agent.dynamic_agents.block_library import BlockLibrary, build_default_block_library
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentBudget
from app.agent.specialists.tools.registry import build_default_observation_registry

_FORBIDDEN_SPEC_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
)

_BUDGET_HARD_CAPS: dict[str, int] = {
    "max_reasoning_calls": 3,
    "max_tool_rounds": 2,
    "max_observations": 12,
    "max_validation_passes": 2,
    "max_runtime_ms": 60000,
}


class AgentSpecValidationError(ValueError):
    """Raised when an `AgentSpec` fails deterministic validation."""


def _budget_violations(budget: DynamicAgentBudget) -> list[str]:
    errors: list[str] = []
    for field_name, cap in _BUDGET_HARD_CAPS.items():
        value = getattr(budget, field_name)
        if value > cap:
            errors.append(f"budget_{field_name}_exceeds_cap:{value}>{cap}")
        if value < 0:
            errors.append(f"budget_{field_name}_negative:{value}")
    return errors


def _forbidden_fields_in_raw(raw: dict[str, Any]) -> list[str]:
    return [f"forbidden_spec_field:{key}" for key in raw if key in _FORBIDDEN_SPEC_FIELD_NAMES]


def _nested_forbidden_fields(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, value in raw.items():
        if key in _FORBIDDEN_SPEC_FIELD_NAMES:
            errors.append(f"forbidden_spec_field:{key}")
        if isinstance(value, dict):
            errors.extend(_nested_forbidden_fields(value))
    return errors


def validate_agent_spec(
    spec: AgentSpec | dict[str, Any],
    *,
    block_library: BlockLibrary | None = None,
    known_observation_names: set[str] | None = None,
) -> list[str]:
    """Return a list of validation errors — empty when valid.

    Never raises for malformed input; unexpected parse failures become errors
    in the returned list instead.
    """
    library = block_library or build_default_block_library()
    observation_names = known_observation_names
    if observation_names is None:
        observation_names = set(build_default_observation_registry().list_names())

    if isinstance(spec, dict):
        errors = _forbidden_fields_in_raw(spec)
        errors.extend(_nested_forbidden_fields(spec))
        try:
            parsed = AgentSpec.model_validate(spec)
        except ValidationError as exc:
            return [*errors, f"invalid_agent_spec:{exc.errors()[0]['type']}"]
        spec = parsed
    else:
        errors: list[str] = []

    if not spec.shadow_only:
        errors.append("shadow_only_must_be_true")

    if spec.validation_policy.allow_writes:
        errors.append("validation_policy_allow_writes_forbidden")

    if spec.validation_policy.allow_proposed_actions:
        errors.append("validation_policy_allow_proposed_actions_forbidden")

    if not spec.role.strip():
        errors.append("role_required")

    if not spec.objective.strip():
        errors.append("objective_required")

    if not spec.expected_output_schema_name.strip():
        errors.append("expected_output_schema_name_required")

    errors.extend(_budget_violations(spec.budget))

    forbidden_keys = set(spec.context_contract.forbidden_context_keys)
    for section in spec.context_contract.allowed_context_sections:
        if section in forbidden_keys:
            errors.append(f"forbidden_context_key_requested:{section}")
    for section in spec.context_contract.required_context_sections:
        if section in forbidden_keys:
            errors.append(f"forbidden_context_key_requested:{section}")

    block_names = list(spec.allowed_blocks) if spec.allowed_blocks else []
    for block_name in block_names:
        block = library.get(block_name)
        if block is None:
            errors.append(f"unknown_block:{block_name}")
            continue
        if block.side_effect_level != "none":
            errors.append(f"block_side_effect_not_none:{block_name}")
        if not block.read_only:
            errors.append(f"block_not_read_only:{block_name}")
        if spec.reasoning_pattern not in block.compatible_reasoning_patterns:
            errors.append(f"incompatible_block:{block_name}")

    for observation_name in spec.allowed_observations:
        if observation_name not in observation_names:
            errors.append(f"unknown_observation:{observation_name}")

    return errors


def require_valid_agent_spec(
    spec: AgentSpec | dict[str, Any],
    *,
    block_library: BlockLibrary | None = None,
    known_observation_names: set[str] | None = None,
) -> AgentSpec:
    """Parse (if needed) and validate — raise `AgentSpecValidationError` on failure."""
    if isinstance(spec, dict):
        try:
            parsed = AgentSpec.model_validate(spec)
        except ValidationError as exc:
            raise AgentSpecValidationError(str(exc)) from exc
        spec = parsed

    errors = validate_agent_spec(
        spec,
        block_library=block_library,
        known_observation_names=known_observation_names,
    )
    if errors:
        raise AgentSpecValidationError("; ".join(errors))
    return spec
