"""Unit tests for the ReasoningBlock-backed grounded answer helper (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.schemas import AgentContextPack
from app.agent.workflows.general_academic_workflow import _grounded_llm_answer
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(text: str) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="completed",
        result={"text": text},
        decision_summary="composed",
        confidence=0.8,
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )


def _context(**overrides: Any) -> AgentContextPack:
    defaults: dict[str, Any] = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="general_academic_question",
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


async def test_uses_reasoning_block_text_when_available():
    fake = FakeReasoningBlock(_completed_output("Here is a grounded catalog answer."))

    text = await _grounded_llm_answer(
        _context(), "What electives are available?", "baseline text", reasoning_block=fake
    )

    assert len(fake.calls) == 1
    assert text == "Here is a grounded catalog answer."


async def test_falls_back_to_baseline_when_reasoning_block_fails():
    fake = FakeReasoningBlock(
        ReasoningBlockOutput(
            status="failed",
            result=None,
            decision_summary="llm unavailable",
            confidence=0.0,
            schema_valid=False,
            iterations_used=0,
            repair_attempts_used=0,
            warnings=["llm_adapter_error: llm_unavailable"],
        )
    )

    text = await _grounded_llm_answer(
        _context(), "What electives are available?", "baseline text", reasoning_block=fake
    )

    assert text == "baseline text"


async def test_missing_llm_configuration_falls_back_without_crashing():
    # Explicit settings (not env/.env-derived) guarantee no API key is
    # configured, regardless of what a developer's local .env contains.
    unconfigured_settings = Settings(**{"OPENAI_API_KEY": None})
    block = ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=unconfigured_settings))

    text = await _grounded_llm_answer(
        _context(), "What electives are available?", "baseline text", reasoning_block=block
    )

    assert text == "baseline text"
