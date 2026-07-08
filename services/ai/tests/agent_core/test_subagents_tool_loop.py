"""Unit tests for `app.agent_core.subagents.tool_loop` -- the new tool-execution
loop `reasoning/` alone doesn't provide (docs/agent/AGENT_VISION.md §6.1, §7.3)."""

from __future__ import annotations

from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockInput
from app.agent_core.subagents.tool_loop import DEFAULT_MAX_ROUNDS, run_subagent_tool_loop
from app.agent_core.tools.default_registry import build_default_tool_registry

_OUTPUT_SCHEMA = {"type": "object"}


def _reasoning_input() -> ReasoningBlockInput:
    return ReasoningBlockInput(
        block_id="blk-1",
        agent_name="retrieval",
        objective="test objective",
        task_context={},
        output_schema_name="test_output_v1",
        output_schema=_OUTPUT_SCHEMA,
        min_reasoning_iterations=1,
        max_reasoning_iterations=1,
    )


def _needs_tool_output(tool_name: str, arguments: dict):
    from app.agent_core.reasoning.schemas import ReasoningBlockOutput, ReasoningToolRequest

    return ReasoningBlockOutput(
        status="needs_tool",
        result=None,
        tool_requests=[ReasoningToolRequest(tool_name=tool_name, purpose="test", arguments=arguments)],
        decision_summary="requesting a tool",
        confidence=0.5,
        schema_valid=False,
        iterations_used=1,
        repair_attempts_used=0,
    )


async def test_tool_not_in_grant_is_recorded_as_failed_and_not_called(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "ok",
                "summary": "done",
                "key_factors": [],
                "missing_context": [],
                "validation_notes": [],
                "warnings": [],
                "tool_requests": [],
                "confidence": 0.9,
                "result": {},
            }
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)
    initial_output = _needs_tool_output("get_entity", {"entity_type": "course", "entity_id": "1"})

    final_output, audit_trail = await run_subagent_tool_loop(
        block=block,
        initial_input=_reasoning_input(),
        initial_output=initial_output,
        tool_grant=[],  # get_entity not granted
        tool_registry=build_default_tool_registry(),
    )

    assert len(audit_trail) == 1
    assert audit_trail[0].tool_name == "get_entity"
    assert audit_trail[0].output_ok is False
    assert final_output.status == "completed"


async def test_granted_tool_is_invoked_and_recorded(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "ok",
                "summary": "done",
                "key_factors": [],
                "missing_context": [],
                "validation_notes": [],
                "warnings": [],
                "tool_requests": [],
                "confidence": 0.9,
                "result": {},
            }
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)
    initial_output = _needs_tool_output("get_entity", {"entity_type": "course", "entity_id": "234218"})

    final_output, audit_trail = await run_subagent_tool_loop(
        block=block,
        initial_input=_reasoning_input(),
        initial_output=initial_output,
        tool_grant=["get_entity"],
        tool_registry=build_default_tool_registry(),
    )

    assert len(audit_trail) == 1
    assert audit_trail[0].tool_name == "get_entity"
    assert audit_trail[0].arguments == {"entity_type": "course", "entity_id": "234218"}
    # The stub always returns not_implemented -- still a real, recorded invocation.
    assert audit_trail[0].output_ok is False
    assert final_output.status == "completed"


async def test_bounded_to_max_rounds_even_if_still_needs_tool(fake_llm_adapter_factory):
    # Every re-invocation also returns needs_tool -- loop must stop at max_rounds.
    responses = [
        {
            "status": "needs_tool",
            "summary": "still need it",
            "key_factors": [],
            "missing_context": [],
            "validation_notes": [],
            "warnings": [],
            "tool_requests": [{"tool_name": "get_entity", "purpose": "x", "arguments": {"entity_type": "course", "entity_id": "1"}}],
            "confidence": 0.5,
            "result": None,
        }
        for _ in range(DEFAULT_MAX_ROUNDS)
    ]
    adapter = fake_llm_adapter_factory(responses)
    block = ReasoningBlock(llm_adapter=adapter)
    initial_output = _needs_tool_output("get_entity", {"entity_type": "course", "entity_id": "1"})

    final_output, audit_trail = await run_subagent_tool_loop(
        block=block,
        initial_input=_reasoning_input(),
        initial_output=initial_output,
        tool_grant=["get_entity"],
        tool_registry=build_default_tool_registry(),
    )

    assert len(adapter.calls) == DEFAULT_MAX_ROUNDS
    assert len(audit_trail) == DEFAULT_MAX_ROUNDS
    assert final_output.status == "needs_tool"
