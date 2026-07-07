"""Unit tests for `app.agent.specialists.requirement_explanation_agent`.

All tests use a fake `ReasoningBlock` — no real LLM call is made.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.prompt_registry import SPECIALIST_REQUIREMENT_EXPLANATION_V1
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.specialists.requirement_explanation_agent import run_requirement_explanation_agent
from app.agent.specialists.schemas import SpecialistAgentInput
from app.config import Settings

_ENABLED_SETTINGS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True)
_DISABLED_SETTINGS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=False)


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None, *, raises: Exception | None = None) -> None:
        self.output = output
        self.raises = raises
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        if self.raises is not None:
            raise self.raises
        assert self.output is not None
        return self.output


def _result(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        status="completed",
        result={"bucket": "faculty_elective", "creditsRequired": 3.0},
        decision_summary="The faculty elective bucket requires 3 credits.",
        key_findings=["3 credits required"],
        missing_context=[],
        warnings=[],
        validation_notes=[],
        sources=[{"type": "degree_requirements"}],
        confidence=0.8,
    )
    defaults.update(overrides)
    return defaults


def _completed_output(result: dict[str, Any], **overrides: Any) -> ReasoningBlockOutput:
    raw_result_confidence = result.get("confidence", 0.8)
    reasoning_output_confidence = max(0.0, min(1.0, float(raw_result_confidence)))
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary=result.get("decision_summary", ""),
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=reasoning_output_confidence,
        schema_valid=True,
        iterations_used=3,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _input(**overrides: Any) -> SpecialistAgentInput:
    defaults: dict[str, Any] = dict(
        subtask_id="s1",
        agent_name="requirement_explanation_agent",
        objective="Explain a degree requirement bucket and what satisfies it.",
        user_message="What is the faculty elective requirement?",
        compiled_context={"agent_context_pack_summary": {"intent": "requirement_explanation"}},
    )
    defaults.update(overrides)
    return SpecialistAgentInput(**defaults)


# 1. Calls ReasoningBlock with the correct prompt contract.
async def test_calls_reasoning_block_with_correct_prompt_contract() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))

    await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_ENABLED_SETTINGS)

    assert len(block.calls) == 1
    assert block.calls[0].prompt_contract_name == SPECIALIST_REQUIREMENT_EXPLANATION_V1


# 2 & 3. Returns structured output preserving subtask_id/agent_name.
async def test_returns_structured_output_preserving_subtask_id_and_agent_name() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))

    output = await run_requirement_explanation_agent(
        _input(subtask_id="explain_bucket"), reasoning_block=block, settings=_ENABLED_SETTINGS
    )

    assert output.subtask_id == "explain_bucket"
    assert output.agent_name == "requirement_explanation_agent"
    assert output.status == "completed"


# 4. Rejects/strips proposed_actions.
async def test_strips_proposed_actions_and_warns() -> None:
    result = _result(proposed_actions=[{"actionType": "save_semester_plan"}])
    block = FakeReasoningBlock(_completed_output(result))

    output = await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_ENABLED_SETTINGS)

    assert output.proposed_actions == []
    assert "specialist_proposed_actions_blocked" in output.warnings


# 5. Fallback works when ReasoningBlock fails.
async def test_fallback_when_reasoning_block_raises() -> None:
    block = FakeReasoningBlock(raises=RuntimeError("boom"))

    output = await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_ENABLED_SETTINGS)

    assert output.status == "skipped"
    assert output.confidence == 0.0
    assert output.proposed_actions == []


# 6. Fallback works when specialist agents are disabled (LLM unavailable path).
async def test_fallback_when_specialist_agents_disabled() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))

    output = await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_DISABLED_SETTINGS)

    assert output.status == "skipped"
    assert "specialist_agents_disabled" in output.warnings
    assert block.calls == []


# 7. Does not expose chain-of-thought fields.
async def test_output_never_exposes_chain_of_thought_fields() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))

    output = await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_ENABLED_SETTINGS)

    dumped_text = str(output.model_dump())
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in dumped_text


# 8. Handles missing context safely.
async def test_handles_missing_context_safely() -> None:
    result = _result(status="needs_more_context", missing_context=["degree_requirements"], confidence=0.15)
    block = FakeReasoningBlock(_completed_output(result))

    output = await run_requirement_explanation_agent(
        _input(compiled_context={}), reasoning_block=block, settings=_ENABLED_SETTINGS
    )

    assert output.status == "needs_more_context"
    assert output.missing_context == ["degree_requirements"]


# 9. Validates confidence range.
async def test_confidence_is_clamped_to_valid_range() -> None:
    block = FakeReasoningBlock(_completed_output(_result(confidence=10.0)))

    output = await run_requirement_explanation_agent(_input(), reasoning_block=block, settings=_ENABLED_SETTINGS)

    assert 0.0 <= output.confidence <= 1.0


# 10. Uses only compact compiled context.
async def test_uses_only_the_supplied_compact_compiled_context() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    compiled_context = {"agent_context_pack_summary": {"intent": "requirement_explanation"}}

    await run_requirement_explanation_agent(
        _input(compiled_context=compiled_context), reasoning_block=block, settings=_ENABLED_SETTINGS
    )

    task_context = block.calls[0].task_context
    assert task_context["compiled_context"] == compiled_context
    assert "raw_context" not in str(task_context)
