"""Safety gating for specialist-agent execution (Phase 10).

Mirrors `supervisor.safety.can_shadow_execute_capability` for the
`specialist_agent` capability type — deliberately conservative and
fail-closed: if any condition is false, ambiguous, or missing, the
capability must NOT be treated as a safe specialist agent.

This module never touches the database, never calls an LLM, and never
executes anything itself — it only inspects a `CapabilityDescriptor`.
"""

from __future__ import annotations

from app.agent.capabilities.schemas import CapabilityDescriptor

SPECIALIST_AGENT_UNSAFE_WARNING_PREFIX = "specialist_agent_not_safe_for_execution"


def is_specialist_agent_safe(capability: CapabilityDescriptor) -> bool:
    """`True` only when every Phase 10 safety condition holds for `capability`.

    All of the following must hold:
    - `capability.type == "specialist_agent"`.
    - `capability.enabled` is `True`.
    - `capability.execution.shadow_execution_supported` is `True`.
    - `capability.execution.safe_for_shadow_execution` is `True`.
    - `capability.execution.side_effect_level == "none"`.
    - `capability.permissions.can_execute_writes` is `False`.
    - `capability.permissions.can_create_action_proposals` is `False`.
    - `capability.permissions.write_scope == "none"`.
    """
    if capability.type != "specialist_agent":
        return False
    if not capability.enabled:
        return False

    execution = capability.execution
    if not execution.shadow_execution_supported:
        return False
    if not execution.safe_for_shadow_execution:
        return False
    if execution.side_effect_level != "none":
        return False

    permissions = capability.permissions
    if permissions.can_execute_writes:
        return False
    if permissions.can_create_action_proposals:
        return False
    if permissions.write_scope != "none":
        return False

    return True


def specialist_agent_unsafe_warning(agent_name: str) -> str:
    """Standard warning string recorded when an agent is refused execution."""
    return f"{SPECIALIST_AGENT_UNSAFE_WARNING_PREFIX}: {agent_name}"
