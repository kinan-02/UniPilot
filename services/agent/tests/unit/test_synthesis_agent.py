"""Unit tests for optional synthesis agent (Phase 21)."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.reasoning.prompt_registry import SYNTHESIS_COMPOSER_V1
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.synthesis.schemas import SynthesisInput
from app.agent.synthesis.synthesis_agent import run_synthesis, run_synthesis_with_llm
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(result: dict[str, Any], **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        decision_summary="composed",
        confidence=0.8,
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _input() -> SynthesisInput:
    return SynthesisInput(
        synthesis_id="syn-llm",
        live_response_summary={"textPreview": "Need 3 credits."},
    )


@pytest.mark.asyncio
async def test_skipped_when_use_llm_false() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=False)
    output = await run_synthesis_with_llm(_input(), settings=cfg, reasoning_block=FakeReasoningBlock())
    assert output.status == "skipped"


@pytest.mark.asyncio
async def test_uses_synthesis_composer_v1_when_enabled() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "candidate_ready",
                "decision_summary": "Composed.",
                "candidate_answer_text": "Need 3 credits.",
                "confidence": 0.8,
                "safe_to_show": True,
                "safe_to_promote": False,
            }
        )
    )
    await run_synthesis_with_llm(_input(), settings=cfg, reasoning_block=fake)
    assert fake.calls
    assert fake.calls[0].prompt_contract_name == SYNTHESIS_COMPOSER_V1


@pytest.mark.asyncio
async def test_invalid_llm_output_falls_back_to_deterministic_synthesis() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(_completed_output({"status": "not_a_status"}, schema_valid=False))
    output = await run_synthesis(_input(), settings=cfg, reasoning_block=fake)
    assert output.status in {"insufficient_evidence", "candidate_ready", "candidate_ready_with_warnings", "unsafe", "needs_clarification"}
    assert any("fallback" in w for w in output.warnings)


@pytest.mark.asyncio
async def test_no_direct_llm_calls() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=False)
    output = await run_synthesis(_input(), settings=cfg, reasoning_block=FakeReasoningBlock())
    assert output.status in {"insufficient_evidence", "candidate_ready", "candidate_ready_with_warnings"}


@pytest.mark.asyncio
async def test_no_proposed_actions_in_output() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "candidate_ready",
                "decision_summary": "Composed.",
                "candidate_answer_text": "Answer",
                "confidence": 0.8,
                "safe_to_show": True,
                "safe_to_promote": False,
            }
        )
    )
    output = await run_synthesis(_input(), settings=cfg, reasoning_block=fake)
    assert "proposed" not in str(output.model_dump()).lower()


@pytest.mark.asyncio
async def test_safe_to_promote_remains_false_when_text_promotion_disabled() -> None:
    cfg = Settings(AGENT_SYNTHESIS_USE_LLM=True, OPENAI_API_KEY="test-key", AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False)
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "candidate_ready",
                "decision_summary": "Composed.",
                "candidate_answer_text": "Answer",
                "confidence": 0.8,
                "safe_to_show": True,
                "safe_to_promote": True,
            }
        )
    )
    output = await run_synthesis(_input(), settings=cfg, reasoning_block=fake)
    assert output.safe_to_promote is False
