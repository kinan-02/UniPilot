"""Tests for `RetrievalReasoningBlock`/`run_retrieval_subagent`
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_retrieval_subagent`
entry point.
"""

from __future__ import annotations

import pytest

from app.agent_core.subagents.retrieval_block import (
    _MAX_ROUNDS,
    run_retrieval_subagent,
)
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolRegistry


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
