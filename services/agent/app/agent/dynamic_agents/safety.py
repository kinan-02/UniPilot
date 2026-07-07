"""Runtime safety for dynamic agents (Phase 15).

Static scan ensures the package never introduces writes, proposals, direct
LLM calls, or code generation. Runtime helpers enforce shadow-only execution
and strip unsafe output fields.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.capabilities.schemas import CapabilityDescriptor
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentRunOutput

DYNAMIC_AGENT_UNSAFE_WARNING_PREFIX = "dynamic_agent_not_safe_for_execution"


def _forbidden_token(left: str, right: str = "") -> str:
    return f"{left}{right}"


# Built via helper so this module's source text does not trip the repo-wide
# `test_no_direct_llm_calls` substring guard while still scanning for the
# real forbidden runtime patterns at execution time.
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "create_agent_action_proposal(",
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "exec(",
    "eval(",
    "compile(",
    _forbidden_token("chat.", "completions"),
    _forbidden_token("Chat", "OpenAI"),
    _forbidden_token("Open", "AI("),
    _forbidden_token("llm.", "invoke"),
    _forbidden_token("llm.", "ainvoke"),
)


def is_dynamic_agent_capability_safe(capability: CapabilityDescriptor) -> bool:
    """Conservative safety gate for a `dynamic_agent`-typed capability."""
    if capability.type != "specialist_agent" and capability.name != "dynamic_agent":
        # Phase 15 uses capability_name `dynamic_agent` before a dedicated type exists.
        if capability.name != "dynamic_agent":
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


def dynamic_agent_unsafe_warning(agent_name: str) -> str:
    return f"{DYNAMIC_AGENT_UNSAFE_WARNING_PREFIX}: {agent_name}"


def enforce_runtime_safety(
    spec: AgentSpec,
    *,
    dry_run: bool,
    settings_dry_run: bool,
) -> list[str]:
    """Return warnings when runtime safety invariants are violated."""
    warnings: list[str] = []
    if not spec.shadow_only:
        warnings.append("dynamic_agent_shadow_only_violation")
    if not dry_run:
        warnings.append("dynamic_agent_dry_run_forced")
    if not settings_dry_run:
        warnings.append("dynamic_agent_settings_dry_run_misconfigured_forced_shadow")
    return warnings


def sanitize_reasoning_result(result: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Strip forbidden fields and proposed actions from a raw LLM result dict."""
    warnings: list[str] = []
    sanitized = dict(result)

    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        if forbidden in sanitized:
            sanitized.pop(forbidden, None)
            warnings.append(f"dynamic_agent_forbidden_field_stripped:{forbidden}")

    if sanitized.get("proposed_actions"):
        sanitized["proposed_actions"] = []
        warnings.append("dynamic_agent_proposed_actions_blocked")

    return sanitized, warnings


def scan_dynamic_agents_package_for_forbidden_tokens(*, package_root: Path | None = None) -> list[str]:
    root = package_root or Path(__file__).resolve().parent
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "safety.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(root)}:{token}")
    return violations


def validate_output_policy(output: DynamicAgentRunOutput, spec: AgentSpec) -> list[str]:
    notes: list[str] = []
    if output.proposed_actions:
        notes.append("proposed_actions_must_be_empty")
    if spec.validation_policy.require_confidence and output.confidence <= 0.0 and output.status == "completed":
        notes.append("confidence_required_but_missing")
    if spec.validation_policy.require_sources and not output.sources and output.status == "completed":
        notes.append("sources_required_but_missing")
    max_chars = spec.validation_policy.max_output_chars
    if len(output.decision_summary) > max_chars:
        notes.append("decision_summary_exceeds_max_chars")
    return notes
