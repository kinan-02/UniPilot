"""Bounded tool-execution loop for a subagent (docs/agent/AGENT_VISION.md §6.1, §7.3).

**New code, not a port.** `agent_core.reasoning.reasoning_block.ReasoningBlock`
has no tool-execution loop of its own -- when a pass reports
`status="needs_tool"`, it returns immediately (see
`reasoning_block.py::_early_exit_output`). The old `services/agent`
equivalent (`specialists/base.py` + `specialists/tools/tool_loop.py`) is
tightly coupled to the retired `SpecialistAgentInput`/observation-registry
world, so this module mirrors its *shape* only (bounded rounds, validate
requested tool names against a grant, execute, re-inject, re-invoke) against
the new, generic `ToolRegistry`.
"""

from __future__ import annotations

import logging

from app.agent_core.planning.state import ToolInvocationRecord
from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent_core.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROUNDS = 2


async def run_subagent_tool_loop(
    *,
    block: ReasoningBlock,
    initial_input: ReasoningBlockInput,
    initial_output: ReasoningBlockOutput,
    tool_grant: list[str],
    tool_registry: ToolRegistry,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> tuple[ReasoningBlockOutput, list[ToolInvocationRecord]]:
    """Round-trip a subagent's `needs_tool` requests through `tool_registry`.

    Never raises: a tool call that isn't in `tool_grant`, isn't registered,
    or fails on invocation is recorded as `output_ok=False` and simply
    doesn't get appended to task_context -- the next reasoning pass sees
    whatever *did* succeed, never a placeholder pretending it worked.
    """
    audit_trail: list[ToolInvocationRecord] = []
    current_output = initial_output
    current_input = initial_input
    rounds_used = 0

    while current_output.status == "needs_tool" and rounds_used < max_rounds:
        rounds_used += 1
        tool_results: dict[str, dict] = dict(current_input.task_context.get("tool_results") or {})

        for request in current_output.tool_requests:
            tool_name = request.tool_name
            if tool_name not in tool_grant:
                audit_trail.append(
                    ToolInvocationRecord(tool_name=tool_name, arguments=request.arguments, output_ok=False)
                )
                logger.warning("subagent_tool_not_in_grant", extra={"toolName": tool_name})
                continue

            try:
                descriptor = tool_registry.get(tool_name)
            except ToolNotFoundError:
                audit_trail.append(
                    ToolInvocationRecord(tool_name=tool_name, arguments=request.arguments, output_ok=False)
                )
                logger.warning("subagent_tool_not_registered", extra={"toolName": tool_name})
                continue

            try:
                tool_input = descriptor.input_model(**request.arguments)
                envelope = await descriptor.callable(tool_input)
            except Exception:  # noqa: BLE001 -- a tool bug must never crash the subagent
                logger.exception("subagent_tool_call_failed", extra={"toolName": tool_name})
                audit_trail.append(
                    ToolInvocationRecord(tool_name=tool_name, arguments=request.arguments, output_ok=False)
                )
                continue

            audit_trail.append(
                ToolInvocationRecord(
                    tool_name=tool_name,
                    arguments=request.arguments,
                    output_ok=envelope.ok,
                    output_certainty=envelope.certainty,
                )
            )
            if envelope.ok:
                tool_results[tool_name] = envelope.model_dump(mode="json")

        current_input = current_input.model_copy(
            update={"task_context": {**current_input.task_context, "tool_results": tool_results}}
        )
        current_output = await block.run(current_input)

    return current_output, audit_trail


__all__ = ["DEFAULT_MAX_ROUNDS", "run_subagent_tool_loop"]
