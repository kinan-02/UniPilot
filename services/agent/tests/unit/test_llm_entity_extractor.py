"""Unit tests for the ReasoningBlock-backed entity extraction fallback."""

from __future__ import annotations

from typing import Any

from app.agent.llm_entity_extractor import resolve_entities_with_llm_fallback
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(result: dict[str, Any] | None, **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        tool_requests=[],
        decision_summary="extracted",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.85,
        schema_valid=True,
        iterations_used=1,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _null_result(**overrides: Any) -> dict[str, Any]:
    base = {
        "courseNumber": None,
        "trackSlug": None,
        "programSlug": None,
        "wikiSlug": None,
    }
    base.update(overrides)
    return base


def _settings_with_key(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "OPENAI_API_KEY": "sk-test",
        "AGENT_LLM_ENTITY_EXTRACTION_FALLBACK_ENABLED": True,
    }
    base.update(overrides)
    return Settings(**base)


async def test_recovers_course_number_when_regex_found_nothing():
    fake = FakeReasoningBlock(_completed_output(_null_result(courseNumber="234004")))
    settings = _settings_with_key()

    merged = await resolve_entities_with_llm_fallback(
        "what's the deal with 234004",
        resolved_entities={},
        settings=settings,
        reasoning_block=fake,
    )

    assert len(fake.calls) == 1
    assert merged["courseNumber"] == "234004"


async def test_never_overwrites_a_regex_resolved_course_number():
    fake = FakeReasoningBlock()
    settings = _settings_with_key()

    merged = await resolve_entities_with_llm_fallback(
        "is 234004 offered next semester",
        resolved_entities={"courseNumber": "234004"},
        settings=settings,
        reasoning_block=fake,
    )

    # Regex already found a core entity -- the LLM fallback must never be called.
    assert fake.calls == []
    assert merged == {"courseNumber": "234004"}


async def test_does_not_overwrite_when_llm_returns_a_different_value(monkeypatch):
    """Even if somehow invoked, an existing entity must never be replaced."""
    fake = FakeReasoningBlock(_completed_output(_null_result(courseNumber="999999")))
    settings = _settings_with_key()

    merged = await resolve_entities_with_llm_fallback(
        "a message that would not normally trigger fallback",
        resolved_entities={"courseNumber": "234004"},
        settings=settings,
        reasoning_block=fake,
    )

    # Not called (existing entity present), value unchanged either way.
    assert fake.calls == []
    assert merged["courseNumber"] == "234004"


async def test_skips_very_short_messages():
    fake = FakeReasoningBlock()
    settings = _settings_with_key()

    merged = await resolve_entities_with_llm_fallback(
        "ok", resolved_entities={}, settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert merged == {}


async def test_does_not_call_reasoning_block_when_flag_disabled():
    fake = FakeReasoningBlock()
    settings = _settings_with_key(AGENT_LLM_ENTITY_EXTRACTION_FALLBACK_ENABLED=False)

    merged = await resolve_entities_with_llm_fallback(
        "what's the deal with 234004",
        resolved_entities={},
        settings=settings,
        reasoning_block=fake,
    )

    assert fake.calls == []
    assert merged == {}


async def test_falls_back_to_existing_entities_when_reasoning_block_fails():
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

    merged = await resolve_entities_with_llm_fallback(
        "what's the deal with 234004",
        resolved_entities={},
        settings=settings,
        reasoning_block=fake,
    )

    assert merged == {}


async def test_missing_llm_configuration_falls_back_without_crashing():
    settings = _settings_with_key(**{"OPENAI_API_KEY": None})

    merged = await resolve_entities_with_llm_fallback(
        "what's the deal with 234004",
        resolved_entities={},
        settings=settings,
    )

    assert merged == {}


async def test_recovers_track_slug_and_preserves_other_entities():
    fake = FakeReasoningBlock(_completed_output(_null_result(trackSlug="track-biomedical-engineering")))
    settings = _settings_with_key()

    merged = await resolve_entities_with_llm_fallback(
        "am I on track for biomedical engineering",
        resolved_entities={"maxCredits": 18},
        settings=settings,
        reasoning_block=fake,
    )

    assert merged["trackSlug"] == "track-biomedical-engineering"
    assert merged["maxCredits"] == 18
