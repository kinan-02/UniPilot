"""Unit tests for the ReasoningBlock-backed LLM intent classifier fallback (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.llm_intent_classifier import (
    classify_intent_with_llm_fallback,
    classify_intent_rules,
)
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings

_LOW_CONFIDENCE_MESSAGE = "hello there"  # falls through to general_academic_question, confidence 0.5


class FakeReasoningBlock:
    """Duck-typed stand-in for `ReasoningBlock` — no real LLM call is made."""

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
        decision_summary="classified",
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
    base = {"OPENAI_API_KEY": "sk-test", "AGENT_LLM_INTENT_FALLBACK_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


async def test_calls_reasoning_block_when_enabled_and_rules_are_low_confidence():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "intent": "course_question",
                "confidence": 0.95,
                "requiresFile": False,
                "requiresConfirmation": False,
                "requiredContext": ["course_record"],
            }
        )
    )
    settings = _settings_with_key()

    result = await classify_intent_with_llm_fallback(
        _LOW_CONFIDENCE_MESSAGE, settings=settings, reasoning_block=fake
    )

    assert len(fake.calls) == 1
    assert result.intent == "course_question"
    assert result.confidence == 0.95
    assert result.required_context == ["course_record"]


async def test_returns_compatible_intent_classification_object():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "intent": "graduation_progress_check",
                "confidence": 0.88,
                "requiresFile": False,
                "requiresConfirmation": False,
                "requiredContext": [],
            }
        )
    )
    settings = _settings_with_key()

    result = await classify_intent_with_llm_fallback(
        _LOW_CONFIDENCE_MESSAGE, settings=settings, reasoning_block=fake
    )

    assert type(result) is type(classify_intent_rules(_LOW_CONFIDENCE_MESSAGE))
    assert result.intent == "graduation_progress_check"
    assert result.requires_file is False
    assert result.requires_confirmation is False


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
    rules_result = classify_intent_rules(_LOW_CONFIDENCE_MESSAGE)

    result = await classify_intent_with_llm_fallback(
        _LOW_CONFIDENCE_MESSAGE, settings=settings, reasoning_block=fake
    )

    assert result == rules_result


async def test_rejects_invalid_unknown_intent_enum_values():
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "intent": "not_a_real_intent",
                "confidence": 0.99,
                "requiresFile": False,
                "requiresConfirmation": False,
                "requiredContext": [],
            }
        )
    )
    settings = _settings_with_key()

    result = await classify_intent_with_llm_fallback(
        _LOW_CONFIDENCE_MESSAGE, settings=settings, reasoning_block=fake
    )

    # An unknown intent value falls back to the safe default rather than
    # ever reaching the caller as an invalid `AgentIntent`.
    assert result.intent == "general_academic_question"


async def test_does_not_call_reasoning_block_when_flag_disabled():
    fake = FakeReasoningBlock()
    settings = _settings_with_key(AGENT_LLM_INTENT_FALLBACK_ENABLED=False)

    result = await classify_intent_with_llm_fallback(
        _LOW_CONFIDENCE_MESSAGE, settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert result == classify_intent_rules(_LOW_CONFIDENCE_MESSAGE)


async def test_does_not_call_reasoning_block_when_rules_are_already_confident():
    fake = FakeReasoningBlock()
    settings = _settings_with_key()

    result = await classify_intent_with_llm_fallback(
        "What am I missing to graduate?", settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert result.intent == "graduation_progress_check"


async def test_missing_llm_configuration_falls_back_without_crashing():
    """No fake block injected: real `ChatLLMAdapter` with no API key must fail safely."""
    settings = _settings_with_key(**{"OPENAI_API_KEY": None})

    result = await classify_intent_with_llm_fallback(_LOW_CONFIDENCE_MESSAGE, settings=settings)

    assert result == classify_intent_rules(_LOW_CONFIDENCE_MESSAGE)
