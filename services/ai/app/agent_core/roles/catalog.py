"""Roster-derived specialist capability catalog for the Specialist Router
(docs/planning/SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md).

The router decides which specialist type(s) execute a step. Its model of what
each specialist can and cannot do MUST match the actual roster, or it will
route work to a specialist that cannot do it (e.g. asking retrieval to derive a
GPA). Rendering that model deterministically from `RoleDefinition`
(`routing_capability` + `tool_grant_ceiling`) makes drift structurally
impossible -- there is no second, hand-maintained copy to fall out of sync.
"""

from __future__ import annotations

from app.agent_core.planning.schemas import RoleName
from app.agent_core.roles.schemas import RoleDefinition

# Deterministic order so the rendered catalog is stable across runs (a set's
# iteration order would make prompts, and prompt-cache keys, nondeterministic).
_CATALOG_ORDER: tuple[RoleName, ...] = (
    "retrieval",
    "interpretation",
    "calculation_validation",
    "simulation_planning",
    "composition",
)


def _role_line(role: RoleDefinition) -> str:
    tools = ", ".join(role.tool_grant_ceiling) if role.tool_grant_ceiling else None
    tool_clause = f" Tools: {tools}." if tools else " (no tools)."
    return f"- {role.name} -- {role.routing_capability}{tool_clause}"


def render_specialist_catalog(roster: dict[RoleName, RoleDefinition]) -> str:
    """One line per specialist: name, its routing_capability sentence, and its
    actual tool grant (or an explicit 'no tools' marker for composition). Roles
    present in `roster` are rendered in `_CATALOG_ORDER`; any extra roles follow
    in sorted order so a newly-added specialist is never silently dropped."""
    ordered = [name for name in _CATALOG_ORDER if name in roster]
    extras = sorted(name for name in roster if name not in _CATALOG_ORDER)
    lines = [_role_line(roster[name]) for name in (*ordered, *extras)]
    return "\n".join(lines)


__all__ = ["render_specialist_catalog"]
