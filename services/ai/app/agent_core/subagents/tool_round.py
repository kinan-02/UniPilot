"""Shared tool-round execution helper for dedicated per-round reasoning
blocks (`RetrievalReasoningBlock`, `InterpretationReasoningBlock`, ...).

Executes one round's worth of LLM-requested tool calls against a
`ToolRegistry`, respecting a `tool_grant` allowlist. Never raises: an
ungranted, unregistered, or raising tool call is recorded `output_ok=False`
in the audit trail and simply omitted from the merged results -- the
caller's round loop continues with whatever DID succeed.

Extracted from `retrieval_block.py`'s own inlined version once
`interpretation_block.py` needed the identical logic -- real, demonstrated
repetition across two call sites, not a speculative abstraction.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.planning.state import ToolInvocationRecord
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger(__name__)


async def execute_tool_round(
    *,
    tool_requests: list[dict[str, Any]],
    tool_grant: list[str],
    tool_registry: ToolRegistry,
    tool_results_so_far: dict[str, Any],
    log_prefix: str = "tool_round",
    tool_call_cache: ToolCallCache | None = None,
) -> tuple[dict[str, Any], list[ToolInvocationRecord]]:
    """Returns a NEW merged results dict (never mutates `tool_results_so_far`)
    plus this round's new audit records."""
    merged_results = dict(tool_results_so_far)
    audit_records: list[ToolInvocationRecord] = []

    for request in tool_requests:
        tool_name = request.get("tool_name")
        arguments = request.get("arguments") or {}
        result_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"

        if tool_name not in tool_grant:
            audit_records.append(ToolInvocationRecord(tool_name=tool_name, arguments=arguments, output_ok=False))
            logger.warning("%s_tool_not_in_grant", log_prefix, extra={"toolName": tool_name})
            continue

        # Fast path, no lock: a sibling nested sub-plan (or an earlier round
        # in this same one) may have already paid for this exact call --
        # found via a live-eval run where the identical get_entity/
        # search_knowledge call recurred dozens of times in one turn because
        # nothing outlived any single block instance.
        cached = tool_call_cache.get(result_key) if tool_call_cache is not None else None
        if cached is not None:
            merged_results[result_key] = cached["envelope"]
            audit_records.append(
                ToolInvocationRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    output_ok=True,
                    output_certainty=cached["certainty"],
                    from_cache=True,
                )
            )
            logger.info("%s_tool_cache_hit tool=%s arguments=%s", log_prefix, tool_name, arguments)
            continue

        try:
            descriptor = tool_registry.get(tool_name)
        except ToolNotFoundError:
            audit_records.append(ToolInvocationRecord(tool_name=tool_name, arguments=arguments, output_ok=False))
            logger.warning("%s_tool_not_registered", log_prefix, extra={"toolName": tool_name})
            continue

        async def _invoke_and_record(
            *, tool_name: str = tool_name, arguments: dict[str, Any] = arguments, descriptor=descriptor
        ) -> None:
            try:
                tool_input = descriptor.input_model(**arguments)
                envelope = await descriptor.callable(tool_input)
            except Exception:  # noqa: BLE001 -- a tool bug must never crash the subagent
                logger.exception("%s_tool_call_failed", log_prefix, extra={"toolName": tool_name})
                audit_records.append(ToolInvocationRecord(tool_name=tool_name, arguments=arguments, output_ok=False))
                return

            audit_records.append(
                ToolInvocationRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    output_ok=envelope.ok,
                    output_certainty=envelope.certainty,
                )
            )
            logger.info(
                "%s_tool_invoked tool=%s ok=%s error=%s arguments=%s",
                log_prefix,
                tool_name,
                envelope.ok,
                envelope.error,
                arguments,
            )
            if envelope.ok:
                dumped = envelope.model_dump(mode="json")
                merged_results[result_key] = dumped
                if tool_call_cache is not None:
                    tool_call_cache.set(result_key, {"envelope": dumped, "certainty": envelope.certainty})

        if tool_call_cache is None:
            await _invoke_and_record()
            continue

        # `orchestrator/parallel_dispatch.py` dispatches a whole execution
        # layer concurrently -- several sibling steps can all reach the fast
        # path above at once, all see a miss (none has finished yet), and
        # all pay for a real call. Acquire the per-key lock and re-check
        # inside it: a concurrent request for the SAME key now blocks until
        # whichever coroutine got here first has actually populated the
        # cache, instead of racing it.
        async with tool_call_cache.lock_for(result_key):
            cached = tool_call_cache.get(result_key)
            if cached is not None:
                merged_results[result_key] = cached["envelope"]
                audit_records.append(
                    ToolInvocationRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                        output_ok=True,
                        output_certainty=cached["certainty"],
                        from_cache=True,
                    )
                )
                logger.info("%s_tool_cache_hit tool=%s arguments=%s", log_prefix, tool_name, arguments)
            else:
                await _invoke_and_record()

    return merged_results, audit_records


__all__ = ["execute_tool_round"]
