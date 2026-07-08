"""Assembles a fresh `ToolRegistry` with all 10 generic primitives (stub, see
docs/agent/AGENT_VISION.md §5). All read-only/compute at this stage --
every callable currently returns `not_implemented`."""

from __future__ import annotations

from app.agent_core.tools.primitives import (
    apply_deterministic_rule,
    compose_answer,
    extract_temporal_pattern,
    get_entity,
    interpret_text,
    mutate_state,
    propose_action,
    search_knowledge,
    search_over_state,
    traverse_relationship,
)
from app.agent_core.tools.registry import ToolRegistry

_ALL_DESCRIPTOR_MODULES = (
    get_entity,
    search_knowledge,
    traverse_relationship,
    interpret_text,
    extract_temporal_pattern,
    apply_deterministic_rule,
    mutate_state,
    search_over_state,
    compose_answer,
    propose_action,
)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in _ALL_DESCRIPTOR_MODULES:
        registry.register(module.DESCRIPTOR)
    return registry


__all__ = ["build_default_tool_registry"]
