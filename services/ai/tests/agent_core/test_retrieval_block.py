"""Tests for `RetrievalReasoningBlock`/`run_retrieval_subagent`
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_retrieval_subagent`
entry point.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.subagents.retrieval_block import (
    _DEGRADED_FINALIZE_CONFIDENCE,
    _MAX_ROUNDS,
    run_retrieval_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolRegistry


class _NeedToolsThenTransientFailAdapter:
    """Round 1 asks for a tool (so a real tool runs and results accumulate);
    the next round's LLM call raises a transient `llm_call_failed` -- the
    mid-loop transport blip that used to discard the whole retrieval step and
    every fact its earlier rounds already fetched.
    """

    def __init__(self, tool_requests: list[dict[str, Any]], *, failure_code: str = "llm_call_failed") -> None:
        self._first: dict[str, Any] = {"status": "need_tools", "tool_requests": tool_requests}
        self._failure_code = failure_code
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return self._first
        raise LLMAdapterError(self._failure_code)

    async def complete_text(self, **_: Any) -> str:
        raise AssertionError("retrieval block does not use complete_text")


class _AlwaysTransientFailAdapter:
    """Every LLM call raises `llm_call_failed` -- the failure hits round 1
    before any tool runs, so there is nothing to salvage."""

    def __init__(self, *, failure_code: str = "llm_call_failed") -> None:
        self._failure_code = failure_code
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        raise LLMAdapterError(self._failure_code)

    async def complete_text(self, **_: Any) -> str:
        raise AssertionError("retrieval block does not use complete_text")


def _context_package(tool_grant=("get_entity", "search_knowledge", "traverse_relationship")) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Fetch the prerequisite.",
        structured_fields=StepInstructionFields(goal="Fetch the prerequisite.", description="Fetch it."),
        dependency_state=[],
        tool_grant=list(tool_grant),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


class _CountingToolRegistry:
    def __init__(self, inner: ToolRegistry) -> None:
        self._inner = inner
        self.call_count = 0

    def get(self, name: str):
        descriptor = self._inner.get(name)
        original_callable = descriptor.callable

        async def _counting_callable(payload):
            self.call_count += 1
            return await original_callable(payload)

        return descriptor.model_copy(update={"callable": _counting_callable})

    def has(self, name: str) -> bool:
        return self._inner.has(name)


def _ready_result(facts=None, basis="wiki_derived"):
    return {
        "status": "ready",
        "result": {
            "certainty_basis": basis,
            "confidence": 1.0,
            "facts": facts or {"found": True},
        }
    }


async def test_round_1_ready_completes_immediately(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_ready_result()])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 0
    assert len(adapter.calls) == 1


async def test_one_round_of_tool_calls_then_ready_happy_path(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "123456", "entity_type": "course"}}]
        },
        _ready_result({"key": "value"})
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1
    assert len(adapter.calls) == 2
    assert len(result.tool_audit_trail) == 1


async def test_tool_called_twice_in_same_round_with_different_arguments_does_not_clobber(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}},
                {"tool_name": "get_entity", "arguments": {"entity_id": "222", "entity_type": "course"}}
            ]
        },
        _ready_result()
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 2
    
    assert len(result.tool_audit_trail) == 2
    args = [t.arguments for t in result.tool_audit_trail]
    assert any(a.get("entity_id") == "111" for a in args)
    assert any(a.get("entity_id") == "222" for a in args)

async def test_malformed_tool_requests_repaired_before_execution(fake_llm_adapter_factory):
    # A live-eval run found the model routinely emitting tool_requests with
    # the wrong keys (e.g. "name"/"params" instead of "tool_name"/
    # "arguments"). Previously that request just silently failed inside
    # execute_tool_round, wasting the whole round. Now the round output goes
    # through the same validate/repair loop the final result already gets.
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [{"name": "get_entity", "params": {"entity_id": "111", "entity_type": "course"}}],
        },
        # Repair call: the model is re-prompted with the schema + errors and
        # fixes the key names.
        {
            "status": "need_tools",
            "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}],
        },
        _ready_result(),
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    # The repaired request reached the real tool call (registry.call_count
    # only increments on an actual invocation) instead of being skipped as
    # unresolvable, which is what happened before this fix.
    assert registry.call_count == 1
    assert len(result.tool_audit_trail) == 1
    assert result.tool_audit_trail[0].tool_name == "get_entity"
    # round1 (malformed) + repair + finalize ready = 3 LLM calls.
    assert len(adapter.calls) == 3


async def test_tool_not_in_grant_skipped_without_aborting_round(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "search_knowledge", "arguments": {"query": "q"}}, # Not granted
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}  # Granted
            ]
        },
        _ready_result()
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(tool_grant=("get_entity",)),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert registry.call_count == 1  # Only get_entity was actually executed
    
    assert len(result.tool_audit_trail) == 2
    # search_knowledge should be ok=False
    assert result.tool_audit_trail[0].tool_name == "search_knowledge"
    assert result.tool_audit_trail[0].output_ok is False


async def test_tool_call_that_raises_skipped_without_aborting_round(fake_llm_adapter_factory):
    class ThrowingRegistry(_CountingToolRegistry):
        def get(self, name: str):
            descriptor = self._inner.get(name)
            if name == "search_knowledge":
                async def _throw(*args, **kwargs):
                    raise RuntimeError("simulated error")
                return descriptor.model_copy(update={"callable": _throw})
            return super().get(name)

    adapter = fake_llm_adapter_factory([
        {
            "status": "need_tools",
            "tool_requests": [
                {"tool_name": "search_knowledge", "arguments": {"query": "q"}},
                {"tool_name": "get_entity", "arguments": {"entity_id": "111", "entity_type": "course"}}
            ]
        },
        _ready_result()
    ])
    registry = ThrowingRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(result.tool_audit_trail) == 2
    assert result.tool_audit_trail[0].tool_name == "search_knowledge"
    assert result.tool_audit_trail[0].output_ok is False


async def test_round_budget_exhausted_forces_finalize_and_fails_closed_if_no_result(fake_llm_adapter_factory):
    # Model always wants more tools, never status=ready
    responses = [
        {"status": "need_tools", "tool_requests": []} for _ in range(_MAX_ROUNDS)
    ]
    # The last round is forced to finalize, but the model ignores it and returns no result
    adapter = fake_llm_adapter_factory(responses)
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert len(adapter.calls) == _MAX_ROUNDS
    assert any("round_budget_exhausted" in w for w in result.warnings)
    
    # Check that the last round's prompt actually included the finalize instruction
    last_prompt = adapter.calls[-1]["user_prompt"]
    assert "NO MORE TOOL CALLS" in last_prompt


async def test_malformed_result_on_finalize_triggers_repair(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        {
            "status": "ready",
            "result": {"certainty_basis": "official_record"} # Missing required 'confidence' and 'facts'
        },
        # Repair call response
        {
            "certainty_basis": "official_record",
            "confidence": 1.0,
            "facts": {"found": True}
        }
    ])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "succeeded"
    assert len(adapter.calls) == 2
    repair_prompt = adapter.calls[1]["user_prompt"]
    assert "schema validation" in repair_prompt


async def test_repair_exhausted_fails_closed(fake_llm_adapter_factory):
    bad_response = {
        "status": "ready",
        "result": {"certainty_basis": "official_record"} # Missing 'facts'
    }
    bad_repair = {"certainty_basis": "official_record"}
    adapter = fake_llm_adapter_factory([bad_response, bad_repair, bad_repair])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert any("schema_repair_exhausted" in w for w in result.warnings)


async def test_transient_llm_failure_mid_loop_salvages_accumulated_tool_results():
    """A transient `llm_call_failed` on a round's LLM call, AFTER earlier
    rounds already fetched facts, must finalize on those facts instead of
    discarding the whole step. Regression for the multi_prereq live-eval case
    where a mid-loop transport blip failed step 1a with an empty audit trail
    and forced an expensive Planner re-plan.
    """
    adapter = _NeedToolsThenTransientFailAdapter(
        [{"tool_name": "get_entity", "arguments": {"entity_id": "123456", "entity_type": "course"}}]
    )
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    # Finalized rather than failed.
    assert result.status == "succeeded"
    assert result.result is not None
    # The facts gathered before the blip survive.
    assert result.result["facts"], "salvaged facts must not be empty"
    assert len(result.tool_audit_trail) == 1
    # Degradation is explicit and honestly low-confidence, so a downstream
    # success-check treats this as partial rather than fully trustworthy.
    assert result.certainty.confidence == _DEGRADED_FINALIZE_CONFIDENCE
    assert any("retrieval_degraded_partial_finalize" in w for w in result.warnings)
    # Exactly two LLM calls: the need_tools round + the failing round. The
    # salvage itself spends NO extra LLM call.
    assert len(adapter.calls) == 2


async def test_transient_llm_failure_before_any_tools_fails_closed():
    """When the transient failure hits before any tool has run, there is
    nothing to salvage, so the step must still fail closed rather than
    fabricate an empty-facts answer."""
    adapter = _AlwaysTransientFailAdapter()
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status == "failed"
    assert not any("retrieval_degraded_partial_finalize" in w for w in result.warnings)
    assert registry.call_count == 0


async def test_returns_subagent_result_shape_matching_generic_paths_output(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_ready_result()])
    registry = _CountingToolRegistry(build_default_tool_registry())

    result = await run_retrieval_subagent(
        context_package=_context_package(),
        tool_registry=registry,
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert result.status in ("succeeded", "partial", "failed")
    assert result.certainty is not None
    assert isinstance(result.assumptions, list)
    assert isinstance(result.warnings, list)
    assert isinstance(result.tool_audit_trail, list)
    assert result.needs_another_round is False
