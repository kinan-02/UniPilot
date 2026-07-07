"""Unit tests for the ReasoningBlock-backed retrieval/answer validator (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.llm_answer_validator import validate_retrieval_with_llm
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.schemas import AgentContextPack, ContextValidation
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
        tool_requests=[],
        decision_summary="validated",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.9,
        schema_valid=True,
        iterations_used=3,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _settings_with_key(**overrides: Any) -> Settings:
    base = {"OPENAI_API_KEY": "sk-test", "AGENT_LLM_VALIDATION_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


def _pack(**overrides: Any) -> AgentContextPack:
    defaults: dict[str, Any] = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        validation=ContextValidation(status="partial", warnings=["missing course number"]),
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


async def test_accepts_a_valid_grounded_answer():
    fake = FakeReasoningBlock(
        _completed_output({"sufficient": True, "gaps": [], "reasoning": "Context covers the question."})
    )
    settings = _settings_with_key()

    result = await validate_retrieval_with_llm(
        _pack(), user_message="Can I take 234218?", settings=settings, reasoning_block=fake
    )

    assert len(fake.calls) == 1
    assert result == {"sufficient": True, "gaps": [], "reasoning": "Context covers the question."}


async def test_flags_unsupported_claims_with_gaps():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "sufficient": False,
                "gaps": ["course number", "student profile"],
                "reasoning": "Missing course number to check eligibility.",
            }
        )
    )
    settings = _settings_with_key()

    result = await validate_retrieval_with_llm(
        _pack(), user_message="Can I take this course?", settings=settings, reasoning_block=fake
    )

    assert result is not None
    assert result["sufficient"] is False
    assert "course number" in result["gaps"]


async def test_falls_back_safely_when_llm_unavailable():
    settings = _settings_with_key(**{"OPENAI_API_KEY": None})

    result = await validate_retrieval_with_llm(
        _pack(), user_message="Can I take 234218?", settings=settings
    )

    assert result is None


async def test_falls_back_safely_when_reasoning_block_fails():
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
    settings = _settings_with_key()

    result = await validate_retrieval_with_llm(
        _pack(), user_message="Can I take 234218?", settings=settings, reasoning_block=fake
    )

    assert result is None


async def test_does_not_call_reasoning_block_when_flag_disabled():
    fake = FakeReasoningBlock()
    settings = _settings_with_key(AGENT_LLM_VALIDATION_ENABLED=False)

    result = await validate_retrieval_with_llm(
        _pack(), user_message="Can I take 234218?", settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert result is None
