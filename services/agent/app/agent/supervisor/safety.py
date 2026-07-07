"""Safety gating for real (shadow-executed) capability handlers (Phase 7).

Decides whether a capability may be executed for real, even in shadow
mode, by `app.agent.supervisor.workflow_adapters.ReadOnlyWorkflowAdapterHandler`.
Every check here is deliberately conservative and fails closed: if any
condition is false, ambiguous, or missing, the capability must NOT be
shadow-executed — callers fall back to the safe Phase 6
`DryRunCapabilityHandler` (or, if the capability is explicitly marked
unsafe, a `"skipped"` result) instead.

This module never touches the database, never calls an LLM, and never
executes anything itself — it only inspects a `CapabilityDescriptor`.
"""

from __future__ import annotations

from app.agent.capabilities.schemas import CapabilityDescriptor

SHADOW_EXECUTION_BLOCKED_WARNING_PREFIX = "shadow_execution_not_safe_for_capability"


def can_shadow_execute_capability(capability: CapabilityDescriptor) -> bool:
    """`True` only when every Phase 7 safety condition holds for `capability`.

    All of the following must hold:
    - `capability.enabled` is `True`.
    - `capability.execution.shadow_execution_supported` is `True`.
    - `capability.execution.safe_for_shadow_execution` is `True`.
    - `capability.execution.side_effect_level == "none"`.
    - `capability.permissions.can_execute_writes` is `False`.
    - `capability.permissions.can_create_action_proposals` is `False`.
    - `capability.permissions.write_scope == "none"`.
    """
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


def shadow_execution_blocked_warning(capability_name: str) -> str:
    """Standard warning string recorded when a capability is refused real execution."""
    return f"{SHADOW_EXECUTION_BLOCKED_WARNING_PREFIX}: {capability_name}"


def can_execute_capability_for_real_with_proposals(capability: CapabilityDescriptor) -> bool:
    """`True` only when every safety condition for real, proposal-creating
    execution holds for `capability` (post-Phase-9).

    Wholly separate from `can_shadow_execute_capability` above, which always
    hard-fails a proposal-creating capability regardless of this function's
    result -- this predicate is never consulted by the shadow/diagnostic/
    promotion dispatch path. It is only ever consulted by
    `app.agent.supervisor.runtime._select_handler` when its caller has
    itself explicitly opted in (`allow_proposal_capable_execution=True`),
    which only `app.agent.planner_first_live.run_planner_first_live_turn`
    ever does, and only after its own independent eligibility gate (flag,
    per-workflow allowlist, human-reviewed runtime-readiness manifest at the
    top rung) has already passed.

    All of the following must hold:
    - `capability.enabled` is `True`.
    - `capability.execution.real_execution_supported_with_proposals` is `True`.
    - `capability.execution.side_effect_level == "proposal"`.
    - `capability.permissions.can_create_action_proposals` is `True`.
    - `capability.permissions.can_execute_writes` is `False` (never a direct write).
    - `capability.permissions.write_scope == "proposal_only"`.
    """
    if not capability.enabled:
        return False

    execution = capability.execution
    if not execution.real_execution_supported_with_proposals:
        return False
    if execution.side_effect_level != "proposal":
        return False

    permissions = capability.permissions
    if not permissions.can_create_action_proposals:
        return False
    if permissions.can_execute_writes:
        return False
    if permissions.write_scope != "proposal_only":
        return False

    return True
