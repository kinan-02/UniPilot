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
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry

logger = logging.getLogger(__name__)


async def execute_tool_round(
    *,
    tool_requests: list[dict[str, Any]],
    tool_grant: list[str],
    tool_registry: ToolRegistry,
    tool_results_so_far: dict[str, Any],
    log_prefix: str = "tool_round",
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
) -> tuple[dict[str, Any], list[ToolInvocationRecord]]:
    """Returns a NEW merged results dict (never mutates `tool_results_so_far`)
    plus this round's new audit records."""
    merged_results = dict(tool_results_so_far)
    audit_records: list[ToolInvocationRecord] = []

    for request in tool_requests:
        # `request.get("tool_name")` can be `None` if the LLM's tool request
        # omits the key -- `ToolInvocationRecord.tool_name` is a non-optional
        # `str`, so passing `None` through raises a pydantic `ValidationError`
        # that escapes this function entirely, violating the "never raises"
        # contract documented above (a real live-eval run reproduced this:
        # it turned a single malformed tool request into a full reasoning-
        # block failure instead of one recorded, gracefully-skipped audit
        # entry). Fall back to a clearly-marked placeholder instead.
        tool_name = request.get("tool_name") or "<missing_tool_name>"
        # Defensive: found via a live-eval run where the model emitted
        # {"tool_name": ..., "args": {...}} instead of the schema's own
        # "arguments" key (~15% of tool_requests in that run) -- every such
        # call silently got {} and failed validation, wasting a whole round.
        # Falling back to "args" costs nothing when the model gets it right.
        arguments = request.get("arguments") or request.get("args") or {}
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
            except Exception as e:  # noqa: BLE001 -- a tool bug must never crash the subagent
                logger.exception("%s_tool_call_failed", log_prefix, extra={"toolName": tool_name})
                audit_records.append(ToolInvocationRecord(tool_name=tool_name, arguments=arguments, output_ok=False))
                merged_results[result_key] = {"ok": False, "error": f"Tool execution failed: {str(e)}", "data": {}}
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
            dumped = envelope.model_dump(mode="json")
            merged_results[result_key] = dumped
            if envelope.ok:
                if tool_call_cache is not None:
                    tool_call_cache.set(result_key, {"envelope": dumped, "certainty": envelope.certainty})
                # Detect search_knowledge zero-match results: ok=True but
                # data["matches"] is empty -- a conclusive "nothing exists"
                # signal, not an error.  Record the query string so the
                # Planner never re-schedules the same search.
                if (
                    unresolvable_registry is not None
                    and tool_name == "search_knowledge"
                    and isinstance(envelope.data, dict)
                    and not envelope.data.get("matches")
                ):
                    query_str = arguments.get("query", "")
                    if query_str:
                        unresolvable_registry.record(
                            query_str,
                            f"search_knowledge returned zero matches for '{query_str}'",
                        )
            else:
                # Detect get_entity entity_not_found errors: ok=False with
                # error starting with "entity_not_found:" -- these are NOT
                # cached by ToolCallCache (it only caches ok=True), so every
                # retry re-hits the DB/graph today.  Record the entity
                # identifier so the Planner stops scheduling retries.
                if unresolvable_registry is not None:
                    if (
                        tool_name == "get_entity"
                        and isinstance(envelope.error, str)
                        and envelope.error.startswith("entity_not_found:")
                    ):
                        entity_id = arguments.get("entity_id", "")
                        if entity_id:
                            unresolvable_registry.record(
                                entity_id,
                                f"get_entity returned entity_not_found for '{entity_id}'",
                            )
                    # Detect search_knowledge failures (ok=False) due to missing graph
                    # or missing index. If it fails, the query is effectively unresolvable
                    # for this turn. Record it to stop the Planner from infinitely retrying.
                    elif (
                        tool_name == "search_knowledge"
                        and isinstance(envelope.error, str)
                    ):
                        query_str = arguments.get("query", "")
                        if query_str:
                            unresolvable_registry.record(
                                query_str,
                                f"search_knowledge failed for '{query_str}': {envelope.error}",
                            )

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
