"""`subagent_builder` (docs/agent/AGENT_VISION.md §7): assembles a
`ReasoningBlockInput` from a role + context package. Deterministic,
non-generative -- it only ever assembles from already-decided pieces, never
invents new logic or a new role."""

from __future__ import annotations

from app.agent_core.reasoning.schemas import ReasoningBlockInput, ReasoningToolSpec
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.schemas import SubagentContextPackage
from app.agent_core.tools.registry import ToolRegistry


def _tool_specs(tool_grant: list[str], tool_registry: ToolRegistry) -> list[ReasoningToolSpec]:
    specs: list[ReasoningToolSpec] = []
    for name in tool_grant:
        descriptor = tool_registry.get(name)
        specs.append(
            ReasoningToolSpec(
                name=descriptor.name,
                description=descriptor.description,
                input_schema=descriptor.input_model.model_json_schema(),
            )
        )
    return specs


def build_reasoning_block_input(
    *,
    role: RoleDefinition,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    block_id: str,
) -> ReasoningBlockInput:
    params = role.default_reasoning_params
    return ReasoningBlockInput(
        block_id=block_id,
        agent_name=role.name,
        objective=context_package.structured_fields.goal,
        task_context={
            "rendered_prompt": context_package.rendered_prompt,
            "structured_fields": context_package.structured_fields.model_dump(),
            "dependency_state": [entry.model_dump(mode="json") for entry in context_package.dependency_state],
        },
        available_tools=_tool_specs(context_package.tool_grant, tool_registry),
        constraints=[*role.guardrails, *context_package.guardrails],
        success_criteria=[],
        output_schema_name=context_package.output_schema_name,
        output_schema=context_package.output_schema,
        risk_level=params.risk_level,
        min_reasoning_iterations=params.min_iterations,
        max_reasoning_iterations=params.max_iterations,
        temperature=params.temperature,
        timeout=params.timeout,
        prompt_contract_name=role.prompt_contract_name,
    )


__all__ = ["build_reasoning_block_input"]
