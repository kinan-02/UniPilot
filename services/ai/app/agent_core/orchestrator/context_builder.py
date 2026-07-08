"""`context_builder` (docs/agent/AGENT_VISION.md §7, §7.2): assembles a
bounded `SubagentContextPackage` from a step-prep decision, a role, and the
shared plan-execution state -- only the upstream results the step actually
depends on, never a guess at what might be relevant."""

from __future__ import annotations

from app.agent_core.orchestrator.prompt_builder import render_subagent_prompt
from app.agent_core.planning.state import PlanExecutionState
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.schemas import StepPrepOutput, SubagentContextPackage


def build_subagent_context_package(
    *,
    step_prep: StepPrepOutput,
    role: RoleDefinition,
    state: PlanExecutionState,
) -> SubagentContextPackage:
    dependency_state = state.slice(step_prep.context_requirements)
    rendered_prompt = render_subagent_prompt(step_prep.instruction_fields, role)

    tool_grant = list(role.tool_grant_ceiling)
    if step_prep.tool_grant_override is not None:
        override = set(step_prep.tool_grant_override)
        tool_grant = [name for name in tool_grant if name in override]

    return SubagentContextPackage(
        rendered_prompt=rendered_prompt,
        structured_fields=step_prep.instruction_fields,
        dependency_state=dependency_state,
        tool_grant=tool_grant,
        output_schema_name=step_prep.output_schema_name,
        output_schema=step_prep.output_schema,
        guardrails=list(role.guardrails),
    )


__all__ = ["build_subagent_context_package"]
