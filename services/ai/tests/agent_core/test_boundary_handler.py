"""Tests for `BoundaryHandlingReasoningBlock`'s two-stage generate-then-structure
flow (docs/agent/AGENT_VISION.md).

Stage 1 (`complete_text`, no schema) generates the actual response content;
stage 2 (`complete_json`) structures that raw content into
`BOUNDARY_HANDLER_OUTPUT_SCHEMA`, capped at `_MAX_STRUCTURING_ATTEMPTS`. This
split exists so a stage-1 call can never fail with a JSON-parse error (there
is no parse step at all), and so a stage-2 structuring failure degrades to
serving stage 1's real content as plain text instead of a generic canned
message.
"""

from __future__ import annotations

from app.agent_core.boundary_handler.boundary_handler import (
    BoundaryHandlerInput,
    BoundaryHandlingReasoningBlock,
    BOUNDARY_HANDLER_OUTPUT_SCHEMA,
    BOUNDARY_HANDLER_OUTPUT_SCHEMA_NAME,
    BOUNDARY_HANDLER_V1,
)
from app.agent_core.reasoning.llm_adapter import LLMAdapterError


def _block_input(**overrides) -> BoundaryHandlerInput:
    base = dict(
        block_id="blk-1",
        agent_name="boundary_handler",
        objective="Compose a helpful decline message.",
        original_user_message="Please waive my prerequisite for Data Structures 1.",
        decline_reason="Registration and waivers require administrative system access we don't have.",
        output_schema_name=BOUNDARY_HANDLER_OUTPUT_SCHEMA_NAME,
        output_schema=BOUNDARY_HANDLER_OUTPUT_SCHEMA,
        prompt_contract_name=BOUNDARY_HANDLER_V1,
    )
    base.update(overrides)
    return BoundaryHandlerInput(**base)


async def test_happy_path_structures_stage1_content_on_first_attempt(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        responses=[{"answer_text": "I'm unable to register you or grant waivers.", "confidence": 0.95}],
        text_responses=["I'm unable to register you or grant waivers."],
    )
    block = BoundaryHandlingReasoningBlock(llm_adapter=adapter)

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.answer_text == "I'm unable to register you or grant waivers."
    assert output.confidence == 0.95
    # One complete_text call (stage 1) + one complete_json call (stage 2).
    assert len(adapter.text_calls) == 1
    assert len(adapter.calls) == 1
    assert output.total_llm_calls_used == 2


async def test_stage1_never_raises_json_parse_failure_even_on_non_json_text(fake_llm_adapter_factory):
    # Stage 1's raw content is deliberately unparseable as JSON (it's just
    # prose) -- `complete_text` has no parse step at all, so this must not
    # raise or degrade stage 1 in any way.
    adapter = fake_llm_adapter_factory(
        responses=[{"answer_text": "Sorry, I can't do that -- {not json at all}.", "confidence": 0.8}],
        text_responses=["Sorry, I can't do that -- {not json at all}."],
    )
    block = BoundaryHandlingReasoningBlock(llm_adapter=adapter)

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.answer_text == "Sorry, I can't do that -- {not json at all}."


async def test_structuring_retries_and_recovers_on_second_attempt(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        responses=[
            # Missing required "answer_text" -> genuinely invalid. (A missing
            # "confidence" would NOT trigger a retry anymore -- the normalizer
            # backfills that metadata field's safe default; only a real content
            # gap like the absent answer_text still exercises the retry path.)
            {"confidence": 0.9},
            {"answer_text": "I'm unable to help with that.", "confidence": 0.9},
        ],
        text_responses=["I'm unable to help with that."],
    )
    block = BoundaryHandlingReasoningBlock(llm_adapter=adapter)

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.answer_text == "I'm unable to help with that."
    assert output.confidence == 0.9
    assert len(adapter.text_calls) == 1
    assert len(adapter.calls) == 2
    # The retry re-supplies the original raw_content, not just the failed attempt.
    assert "I'm unable to help with that." in adapter.calls[1]["user_prompt"]


async def test_structuring_exhausted_falls_back_to_raw_stage1_content(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        responses=[
            {"confidence": 0.9},  # invalid: no answer_text (a content gap the backfill won't fill)
            {"confidence": 0.9},  # invalid again
        ],
        text_responses=["Some real, tailored decline message."],
    )
    block = BoundaryHandlingReasoningBlock(llm_adapter=adapter)

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is False
    # The real stage-1 content is preserved, not swapped for the generic
    # canned fallback message.
    assert output.answer_text == "Some real, tailored decline message."
    assert output.confidence == 0.5
    assert "structuring_failed_using_raw_stage1_content" in output.warnings
    assert len(adapter.calls) == 2


async def test_stage1_llm_failure_falls_back_to_canned_message(fake_llm_adapter_factory):
    class _RaisingTextAdapter:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.text_calls: list[dict] = []

        async def complete_json(self, **_kwargs):
            raise AssertionError("stage 2 must not be reached if stage 1 fails")

        async def complete_text(self, **_kwargs):
            raise LLMAdapterError("llm_call_failed_test")

    block = BoundaryHandlingReasoningBlock(llm_adapter=_RaisingTextAdapter())

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is False
    assert "boundary_handler_fallback_used" in output.warnings
    assert "stage1_generation_failed" in output.warnings
    assert output.answer_text  # still a non-empty, user-facing message


async def test_stage1_empty_content_falls_back(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(responses=[], text_responses=["   "])
    block = BoundaryHandlingReasoningBlock(llm_adapter=adapter)

    output = await block.run(_block_input())

    assert output.status == "completed"
    assert output.schema_valid is False
    assert "stage1_empty_content" in output.warnings
    assert len(adapter.calls) == 0  # stage 2 never reached
