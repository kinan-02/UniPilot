"""Ties `subagent_builder` + `ReasoningBlock` + the tool loop together and
adapts the result into a `SubagentResult` (docs/agent/AGENT_VISION.md §7.3).

The adapter (`build_subagent_result`) is deliberately not a type alias: see
`agent_core.reasoning.schemas.ReasoningBlockOutput` for why its status
vocabulary, missing tool-audit-trail, and coarse-only confidence don't map
1:1 onto what a subagent is expected to return.
"""

from __future__ import annotations

from app.agent_core.certainty import CertaintyTag, SourceRef, ToolInvocationRecord
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptRegistry
from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockOutput
from app.agent_core.roles.prompts import build_prompt_registry_with_roles
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.builder import build_reasoning_block_input
from app.agent_core.subagents.schemas import SubagentContextPackage, SubagentResult
from app.agent_core.subagents.tool_loop import run_subagent_tool_loop
from app.agent_core.tools.registry import ToolRegistry

_DEFAULT_CERTAINTY_BASIS = "llm_interpretation"


def build_subagent_result(
    engine_output: ReasoningBlockOutput, tool_audit_trail: list[ToolInvocationRecord]
) -> SubagentResult:
    if engine_output.status == "completed" and engine_output.schema_valid and engine_output.result is not None:
        status = "succeeded"
    elif engine_output.status in ("needs_more_context", "needs_tool"):
        status = "partial"
    else:
        status = "failed"

    result = engine_output.result or {}
    # Each role's own `output_schema` should declare these as explicit result
    # properties (see docs/agent/AGENT_VISION.md §6, per-role prompt
    # contracts) -- `engine_output.confidence` is only a coarse fallback.
    basis = result.get("certainty_basis") or _DEFAULT_CERTAINTY_BASIS
    confidence = result.get("confidence")
    if confidence is None:
        confidence = engine_output.confidence
    source_ref_data = result.get("source_ref")
    source_ref = SourceRef(**source_ref_data) if isinstance(source_ref_data, dict) else None
    assumptions = result.get("assumptions") or []

    return SubagentResult(
        status=status,
        result=engine_output.result,
        certainty=CertaintyTag(basis=basis, confidence=confidence, source_ref=source_ref),
        assumptions=list(assumptions),
        warnings=list(engine_output.warnings),
        tool_audit_trail=tool_audit_trail,
        needs_another_round=engine_output.status == "needs_tool",
    )


async def run_subagent(
    *,
    role: RoleDefinition,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    prompt_registry: PromptRegistry | None = None,
) -> SubagentResult:
    reasoning_input = build_reasoning_block_input(
        role=role, context_package=context_package, tool_registry=tool_registry, block_id=block_id
    )
    block = ReasoningBlock(
        llm_adapter=llm_adapter, prompt_registry=prompt_registry or build_prompt_registry_with_roles()
    )
    output = await block.run(reasoning_input)

    tool_audit_trail: list[ToolInvocationRecord] = []
    if output.status == "needs_tool":
        output, tool_audit_trail = await run_subagent_tool_loop(
            block=block,
            initial_input=reasoning_input,
            initial_output=output,
            tool_grant=context_package.tool_grant,
            tool_registry=tool_registry,
        )

    return build_subagent_result(output, tool_audit_trail)


__all__ = ["build_subagent_result", "run_subagent"]
