"""`compose_answer` at the Orchestrator level (docs/agent/AGENT_VISION.md §9,
§5 primitive 9a): produces the final answer from the accumulated
plan-execution state once the Planner judges the plan complete.

Reuses the Composition role's own subagent machinery directly (zero tool
access, structurally enforced by `RoleDefinition.tool_grant_ceiling == ()`)
rather than a separate, parallel composition mechanism -- it never re-derives
facts, only ever reasons over what `PlanExecutionState` already holds.
"""

from __future__ import annotations

from app.agent_core.planning.state import PlanExecutionState
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.run import run_subagent
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage, SubagentResult
from app.agent_core.tools.registry import ToolRegistry

_COMPOSITION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"answer_text": {"type": "string"}},
    "required": ["answer_text"],
}


async def compose_answer(
    *,
    state: PlanExecutionState,
    user_goal: str,
    composition_role: RoleDefinition,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> SubagentResult:
    if composition_role.tool_grant_ceiling:
        raise ValueError("compose_answer requires a composition role with zero tool grant")

    context_package = SubagentContextPackage(
        rendered_prompt=f"Compose the final answer for: {user_goal}",
        structured_fields=StepInstructionFields(
            goal=user_goal,
            description="Compose a grounded final answer from the accumulated plan-execution state.",
        ),
        dependency_state=list(state.entries),
        tool_grant=[],
        output_schema_name="composition_agent_output_v1",
        output_schema=_COMPOSITION_OUTPUT_SCHEMA,
        guardrails=list(composition_role.guardrails),
    )
    return await run_subagent(
        role=composition_role,
        context_package=context_package,
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=block_id,
    )


__all__ = ["compose_answer"]
