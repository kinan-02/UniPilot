"""Assembles a fresh `ToolRegistry` with the 9 generic primitives
(docs/agent/AGENT_VISION.md §5, all implemented) plus the higher-level
composite tools built on top of them (docs/agent/HIGHER_LEVEL_TOOLS.md).
Both tiers live in the same flat `ToolRegistry` namespace -- composites are
not a separate, role-private mechanism (see HIGHER_LEVEL_TOOLS.md's
"Architecture decision" section)."""

from __future__ import annotations

from app.agent_core.tools.composites import (
    audit_graduation_progress,
    check_eligibility,
    compare_plans,
    find_requirement_substitutes,
    get_course_profile,
    get_current_date,
    get_policy_answer,
    get_track_requirements,
    simulate_course_disruption,
)
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

_ALL_PRIMITIVE_MODULES = (
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

_ALL_COMPOSITE_MODULES = (
    get_policy_answer,
    get_course_profile,
    simulate_course_disruption,
    check_eligibility,
    get_track_requirements,
    compare_plans,
    audit_graduation_progress,
    find_requirement_substitutes,
    get_current_date,
)

_ALL_DESCRIPTOR_MODULES = _ALL_PRIMITIVE_MODULES + _ALL_COMPOSITE_MODULES


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in _ALL_DESCRIPTOR_MODULES:
        registry.register(module.DESCRIPTOR)
    return registry


__all__ = ["build_default_tool_registry"]
