"""Unit tests for `app.agent_core.subagents.tool_loop` -- the new tool-execution
loop `reasoning/` alone doesn't provide (docs/agent/AGENT_VISION.md §6.1, §7.3)."""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockInput
from app.agent_core.subagents.tool_loop import DEFAULT_MAX_ROUNDS, run_subagent_tool_loop
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry

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


class _EchoInput(BaseModel):
    entity_type: str
    entity_id: str


def _always_ok_registry() -> ToolRegistry:
    """A fake `get_entity` that always succeeds, echoing its own arguments
    into `data` -- lets a test tell two distinct successful calls to the
    SAME tool name apart by their result content."""

    async def _callable(payload: _EchoInput) -> ToolOutputEnvelope:
        return ToolOutputEnvelope(ok=True, data={"entityType": payload.entity_type, "entityId": payload.entity_id})

    registry = ToolRegistry()
    registry.register(
        ToolDescriptor(
            name="get_entity",
            description="test double",
            input_model=_EchoInput,
            output_model=ToolOutputEnvelope,
            side_effect="read",
            callable=_callable,
        )
    )
    return registry


async def test_two_distinct_successful_calls_to_the_same_tool_do_not_clobber_each_other(
    fake_llm_adapter_factory,
):
    """Regression guard: `tool_results` used to be keyed by tool name alone,
    so a second successful get_entity call (different arguments) silently
    overwrote the first's result -- found while investigating a live
    Retrieval convergence failure where a completed_courses fetch's result
    was at risk of being erased by a follow-up course-detail call."""
    second_pass_response = {
        "status": "needs_tool",
        "summary": "still enriching",
        "key_factors": [],
        "missing_context": [],
        "validation_notes": [],
        "warnings": [],
        "tool_requests": [
            {
                "tool_name": "get_entity",
                "purpose": "enrich",
                "arguments": {"entity_type": "course", "entity_id": "00440148"},
            }
        ],
        "confidence": 0.5,
        "result": None,
    }
    final_response = {
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
    adapter = fake_llm_adapter_factory([second_pass_response, final_response])
    block = ReasoningBlock(llm_adapter=adapter)
    initial_output = _needs_tool_output(
        "get_entity", {"entity_type": "completed_courses", "entity_id": "user-1"}
    )

    await run_subagent_tool_loop(
        block=block,
        initial_input=_reasoning_input(),
        initial_output=initial_output,
        tool_grant=["get_entity"],
        tool_registry=_always_ok_registry(),
    )

    # The final call's own user_prompt carries every prior tool_results entry
    # accumulated so far -- both the first (completed_courses) and second
    # (course) calls' results must both still be present, under distinct keys.
    final_user_prompt = adapter.calls[-1]["user_prompt"]
    assert "user-1" in final_user_prompt
    assert "00440148" in final_user_prompt
