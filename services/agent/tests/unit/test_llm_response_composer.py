"""Unit tests for the ReasoningBlock-backed response composer (Phase 2)."""

from __future__ import annotations

from typing import Any

from app.agent.llm_response_composer import enhance_response_with_llm, stream_llm_explanation_deltas
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.schemas import AgentContextPack, AgentResponse, ProposedAction, StructuredBlock
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(text: str, **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result={"text": text},
        tool_requests=[],
        decision_summary="composed",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=0.9,
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _settings_with_key(**overrides: Any) -> Settings:
    base = {"OPENAI_API_KEY": "sk-test", "AGENT_LLM_EXPLANATION_ENABLED": True}
    base.update(overrides)
    return Settings(**base)


def _response(**overrides: Any) -> AgentResponse:
    defaults: dict[str, Any] = dict(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="You have 90/120 credits completed.",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"completed": 90, "total": 120})],
        warnings=["one elective missing"],
        suggested_prompts=["What am I missing to graduate?"],
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save plan")
        ],
        assumptions=["assuming next semester is 2025-2"],
        used_sources=["degree_requirements"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _context(**overrides: Any) -> AgentContextPack:
    defaults: dict[str, Any] = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


async def test_enhances_only_text():
    fake = FakeReasoningBlock(_completed_output("You've completed 90 of 120 credits — nice progress!"))
    response = _response()
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert len(fake.calls) == 1
    assert enhanced.text == "You've completed 90 of 120 credits — nice progress!"
    assert enhanced.text != response.text


async def test_does_not_mutate_structured_blocks():
    fake = FakeReasoningBlock(_completed_output("Rewritten explanation."))
    response = _response()
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert enhanced.blocks == response.blocks


async def test_does_not_mutate_proposed_actions():
    fake = FakeReasoningBlock(_completed_output("Rewritten explanation."))
    response = _response()
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert enhanced.proposed_actions == response.proposed_actions


async def test_preserves_warnings_and_sources():
    fake = FakeReasoningBlock(_completed_output("Rewritten explanation."))
    response = _response()
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert enhanced.warnings == response.warnings
    assert enhanced.used_sources == response.used_sources
    assert enhanced.assumptions == response.assumptions
    assert enhanced.suggested_prompts == response.suggested_prompts


async def test_falls_back_to_deterministic_text_on_reasoning_block_failure():
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
    response = _response()
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert enhanced == response


async def test_does_not_call_reasoning_block_when_flag_disabled():
    fake = FakeReasoningBlock()
    response = _response()
    settings = _settings_with_key(AGENT_LLM_EXPLANATION_ENABLED=False)

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings, reasoning_block=fake
    )

    assert fake.calls == []
    assert enhanced == response


async def test_on_delta_callback_receives_final_text_once():
    fake = FakeReasoningBlock(_completed_output("Rewritten explanation."))
    response = _response()
    settings = _settings_with_key()
    deltas: list[str] = []

    async def on_delta(token: str) -> None:
        deltas.append(token)

    await enhance_response_with_llm(
        response,
        context=_context(),
        user_message="How am I doing?",
        settings=settings,
        on_delta=on_delta,
        reasoning_block=fake,
    )

    assert deltas == ["Rewritten explanation."]


async def test_missing_llm_configuration_falls_back_without_crashing():
    response = _response()
    settings = _settings_with_key(**{"OPENAI_API_KEY": None})

    enhanced = await enhance_response_with_llm(
        response, context=_context(), user_message="How am I doing?", settings=settings
    )

    assert enhanced == response


async def test_stream_explanation_deltas_yields_single_final_chunk():
    fake = FakeReasoningBlock(_completed_output("Streamed-in-one-chunk explanation."))
    response = _response()
    settings = _settings_with_key()

    chunks = [
        chunk
        async for chunk in stream_llm_explanation_deltas(
            response,
            context=_context(),
            user_message="How am I doing?",
            settings=settings,
            reasoning_block=fake,
        )
    ]

    assert chunks == ["Streamed-in-one-chunk explanation."]


async def test_skips_llm_rewrite_for_deterministic_eligibility_validation():
    fake = FakeReasoningBlock(_completed_output("Yes — you appear eligible to take course 02360343."))
    response = _response(
        text="No — you do not appear eligible for course 02360343 yet.",
        used_sources=["Deterministic prerequisite eligibility validation"],
    )
    settings = _settings_with_key()

    enhanced = await enhance_response_with_llm(
        response,
        context=_context(intent="course_question"),
        user_message="Can I take 02360343?",
        settings=settings,
        reasoning_block=fake,
    )

    assert fake.calls == []
    assert enhanced.text == response.text

