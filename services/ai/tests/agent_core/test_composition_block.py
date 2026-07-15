"""Tests for `CompositionReasoningBlock`/`run_composition_subagent`
(docs/agent/agent_plans/COMPOSITION_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_composition_subagent` entry point.
"""

from __future__ import annotations

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.reasoning.result_normalizer import GENERIC_BLANK_FIELD_PLACEHOLDER
from app.agent_core.subagents.composition_block import run_composition_subagent
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.planning.state import CertaintyTag


def _context_package() -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Compose the final answer.",
        structured_fields=StepInstructionFields(goal="Write an answer.", description="Write it."),
        dependency_state=[],
        tool_grant=[],  # Composition has no tool access
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
    )


class _ProseOnlyAdapter:
    """Reproduces the live failure (2026-07-15): the composition model answers
    in PROSE rather than JSON, so `complete_json` records the raw text and then
    raises `json_parse_failed`. Structured output is off by default
    (`agent_reasoning_structured_output_enabled: bool = False`), so nothing
    forces the model to emit JSON, and both attempts came back as prose."""

    def __init__(self, prose: str) -> None:
        self.prose = prose
        self.call_count = 0

    async def complete_json(self, *, raw_model_text_out: list[str] | None = None, **_: object) -> dict:
        self.call_count += 1
        if raw_model_text_out is not None:
            # The real adapter records raw text BEFORE raising.
            raw_model_text_out.append(self.prose)
        raise LLMAdapterError("json_parse_failed")

    async def complete_text(self, **_: object) -> str:
        raise AssertionError("composition must not use complete_text")


@pytest.mark.asyncio
async def test_prose_answer_is_salvaged_rather_than_discarded() -> None:
    """A correct answer must not be thrown away over its wrapper.

    Live, the model returned a fully correct answer ("...includes 17 courses...
    00940564: Grade 90...") as prose; the block failed and the student received
    an EMPTY string. For a single-string-field schema the prose IS the
    answer_text, so salvage it instead of losing it."""
    prose = "Here is a list of your completed courses. The data covers three semesters and includes 17 courses."
    adapter = _ProseOnlyAdapter(prose)

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.result is not None
    assert result.result["answer_text"] == prose
    # Retried once before salvaging (parse failures are retried), never silently.
    assert adapter.call_count == 2
    assert any("salvaged" in warning for warning in result.warnings), result.warnings


@pytest.mark.asyncio
async def test_empty_prose_is_not_salvaged() -> None:
    """Salvage only rescues real content -- an empty response is still a
    failure, never an empty 'answer'."""
    adapter = _ProseOnlyAdapter("   ")

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=adapter,
        block_id="test-block",
    )

    assert result.status == "failed"


@pytest.mark.asyncio
async def test_happy_path_returns_succeeded(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            {"answer_text": "The retake policy allows 2 retakes."},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.result == {"answer_text": "The retake policy allows 2 retakes."}
    assert result.certainty == CertaintyTag(basis="llm_interpretation", confidence=1.0)
    assert not result.warnings
    assert not result.tool_audit_trail
    assert len(llm_adapter._responses) == 0


@pytest.mark.asyncio
async def test_malformed_result_triggers_schema_repair_and_recovers(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            {"wrong_key": "Oops"},  # Fails schema
            {"answer_text": "Recovered answer."},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.result == {"answer_text": "Recovered answer."}
    assert len(llm_adapter._responses) == 0


@pytest.mark.asyncio
async def test_schema_repair_exhausted_fails_closed(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            {"wrong_key": "1"},
            {"wrong_key": "2"},
            {"wrong_key": "3"},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "failed"
    assert "composition_failed: schema_validation_failed" in result.warnings
    assert len(llm_adapter._responses) == 0


@pytest.mark.asyncio
async def test_blank_or_placeholder_answer_fails_closed(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            {"answer_text": "   "},
            {"answer_text": "   "},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "failed"
    assert "composition_failed: empty_answer_text" in result.warnings
    assert len(llm_adapter._responses) == 0

    llm_adapter2 = fake_llm_adapter_factory(
        responses=[
            {"answer_text": GENERIC_BLANK_FIELD_PLACEHOLDER},
            {"answer_text": GENERIC_BLANK_FIELD_PLACEHOLDER},
        ]
    )

    result2 = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter2,
        block_id="test-block",
    )

    assert result2.status == "failed"
    assert "composition_failed: empty_answer_text" in result2.warnings


@pytest.mark.asyncio
async def test_retries_once_when_result_is_missing_and_returns_retry_outcome(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            # First attempt fails with empty text (semantic check)
            {"answer_text": "  "},
            # Second attempt succeeds
            {"answer_text": "Retry succeeded."},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.result == {"answer_text": "Retry succeeded."}
    assert len(llm_adapter._responses) == 0


@pytest.mark.asyncio
async def test_does_not_retry_when_the_failure_is_not_result_is_missing(fake_llm_adapter_factory) -> None:
    # We can fake it by raising an LLM error which gives reasoning_block_failed: internal_error.
    class ErrorAdapter:
        async def complete_json(self, *args, **kwargs):
            raise ValueError("Some catastrophic error")

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=ErrorAdapter(),
        block_id="test-block",
    )

    assert result.status == "failed"
    assert "reasoning_block_failed: internal_error" in result.warnings
    # Did not retry
    assert "empty_answer_text" not in result.warnings


@pytest.mark.asyncio
async def test_subagent_result_shape_parity(fake_llm_adapter_factory) -> None:
    llm_adapter = fake_llm_adapter_factory(
        responses=[
            {"answer_text": "Works."},
        ]
    )

    result = await run_composition_subagent(
        context_package=_context_package(),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.certainty.basis == "llm_interpretation"
    assert result.certainty.confidence == 1.0
    assert result.assumptions == []
    assert result.warnings == []
    assert result.tool_audit_trail == []
    assert not result.needs_another_round
