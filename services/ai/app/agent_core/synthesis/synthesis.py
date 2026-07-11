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

# Emitted verbatim by `schema_validator.validate_against_schema` when the
# model's final pass reports status="ok" but leaves `result` entirely absent
# (as opposed to present-but-malformed). The generic schema-repair loop
# (`schema_repair.py`) cannot recover this for Composition specifically: its
# only required field, `answer_text`, IS the content -- "fix the structure,
# do not add new facts" is a contradiction when the fix requires writing the
# missing prose from scratch. A retry of the original pass (fresh model
# attempt over the same facts) is the only recovery that can actually work.
_RESULT_MISSING_MARKER = "result_is_missing"


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
    result = await run_subagent(
        role=composition_role,
        context_package=context_package,
        tool_registry=tool_registry,
        llm_adapter=llm_adapter,
        block_id=block_id,
    )
    if result.status == "failed" and _RESULT_MISSING_MARKER in result.warnings:
        result = await run_subagent(
            role=composition_role,
            context_package=context_package,
            tool_registry=tool_registry,
            llm_adapter=llm_adapter,
            block_id=f"{block_id}-retry",
        )
    return result


__all__ = ["compose_answer"]
