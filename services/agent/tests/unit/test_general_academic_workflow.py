"""Unit tests for the ReasoningBlock-backed grounded answer helper (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.llm_response_composer import ALREADY_LLM_COMPOSED_SOURCE
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.schemas import AgentContextPack, AgentResponse
from app.agent.workflows.general_academic_workflow import GeneralAcademicWorkflow, _grounded_llm_answer
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


async def test_falls_back_to_baseline_when_reasoning_block_returns_placeholder():
    """`_normalize_generic_result` fills a blank required string field with
    `GENERIC_BLANK_FIELD_PLACEHOLDER` ("unknown") to pass schema validation --
    never real content, even though `status="completed"`/`schema_valid=True`."""
    fake = FakeReasoningBlock(_completed_output("unknown"))

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


async def _run_workflow(context: AgentContextPack, user_message: str = "hi") -> AgentResponse:
    events = [
        event async for event in GeneralAcademicWorkflow().run(None, context=context, user_message=user_message)
    ]
    return next(event for event in events if isinstance(event, AgentResponse))


async def test_llm_composed_marker_set_for_general_academic_branch():
    response = await _run_workflow(_context(intent="general_academic_question"))
    assert ALREADY_LLM_COMPOSED_SOURCE in response.used_sources


async def test_llm_composed_marker_set_for_catalog_search_branch():
    response = await _run_workflow(_context(intent="catalog_search"))
    assert ALREADY_LLM_COMPOSED_SOURCE in response.used_sources


async def test_llm_composed_marker_absent_for_unknown_or_unsupported_branch():
    response = await _run_workflow(_context(intent="unknown_or_unsupported"))
    assert ALREADY_LLM_COMPOSED_SOURCE not in response.used_sources


async def test_llm_composed_marker_absent_for_profile_update_branch():
    response = await _run_workflow(_context(intent="profile_update"))
    assert ALREADY_LLM_COMPOSED_SOURCE not in response.used_sources


async def test_baseline_fallback_text_is_honest_when_nothing_retrieved():
    """When there's no wiki/regulation context to ground on and the LLM is
    unavailable (ambient OPENAI_API_KEY blanked for tests), the fallback text
    must be a real, honest message -- not the internal 'Intent: X.' label
    that used to leak straight through as the visible answer."""
    response = await _run_workflow(_context(intent="general_academic_question"))
    assert "Intent:" not in response.text
    assert "don't have enough retrieved catalog" in response.text
