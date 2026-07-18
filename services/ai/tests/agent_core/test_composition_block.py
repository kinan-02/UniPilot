"""Tests for `CompositionReasoningBlock`/`run_composition_subagent`
(docs/agent/agent_plans/COMPOSITION_REASONING_BLOCK_PLAN.md).

All scenarios exercised through the public `run_composition_subagent` entry point.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.reasoning.result_normalizer import GENERIC_BLANK_FIELD_PLACEHOLDER
from app.agent_core.subagents.composition_block import run_composition_subagent
from app.agent_core.subagents.schemas import StepInstructionFields, SubagentContextPackage
from app.agent_core.certainty import CertaintyTag
from app.agent_core.planning.state import StateEntry


def _entry(step_id: str, *, basis: str = "official_record", status: str = "succeeded") -> StateEntry:
    """One piece of evidence an answer gets composed from. `confidence=1.0` is
    the codebase-wide convention for a tool result (`get_entity`,
    `check_eligibility` and friends all emit it) -- the epistemics live in
    `basis`, which is exactly why an answer's grounding has to be read from
    there rather than from a confidence number."""
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status=status,
        output_schema_name="generic_step_output_v1",
        data={"credits_completed": 84.5},
        certainty=CertaintyTag(basis=basis, confidence=1.0),
        produced_at=datetime.now(timezone.utc),
    )


def _context_package(dependency_state: list[StateEntry] | None = None) -> SubagentContextPackage:
    return SubagentContextPackage(
        rendered_prompt="Compose the final answer.",
        structured_fields=StepInstructionFields(goal="Write an answer.", description="Write it."),
        dependency_state=dependency_state if dependency_state is not None else [],
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
        context_package=_context_package([_entry("s1")]),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.result == {"answer_text": "The retake policy allows 2 retakes."}
    assert result.certainty == CertaintyTag(basis="llm_interpretation", confidence=0.9)
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
        context_package=_context_package([_entry("s1")]),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.certainty.basis == "llm_interpretation"
    assert result.certainty.confidence == 0.9
    assert result.assumptions == []
    assert result.warnings == []
    assert result.tool_audit_trail == []
    assert not result.needs_another_round


@pytest.mark.asyncio
async def test_answer_resting_on_an_inferred_fact_is_not_high_confidence(fake_llm_adapter_factory) -> None:
    """F1's shipping symptom, in one test.

    Live (2026-07-16, ise_correctness `credits_remaining`): a deterministic
    credit calculation failed, the replan routed the work to `interpretation`,
    which did the arithmetic in-model, and the answer -- "44.5 credits
    remaining ... high-confidence estimate (95%)" -- shipped banded "high".
    It was wrong. Composition stamped a flat `confidence=1.0` on every
    successful answer, so `certainty_band` could not tell an answer read off an
    official record from one invented by a language model.

    An answer is only as grounded as the weakest fact under it: one
    `llm_interpretation` entry in the evidence is enough to cost it "high".
    """
    llm_adapter = fake_llm_adapter_factory(responses=[{"answer_text": "You have 44.5 credits remaining."}])

    result = await run_composition_subagent(
        context_package=_context_package(
            [
                _entry("s1", basis="official_record"),
                _entry("s2", basis="llm_interpretation"),  # the in-model arithmetic
            ]
        ),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.certainty.confidence == 0.6, (
        "an answer resting on in-model arithmetic was banded the same as one read "
        "straight off an official record"
    )


@pytest.mark.asyncio
async def test_answer_composed_from_nothing_is_low_confidence(fake_llm_adapter_factory) -> None:
    """Prose with no evidence under it at all is the least grounded thing the
    system can emit -- it must never outrank an answer built from records."""
    llm_adapter = fake_llm_adapter_factory(responses=[{"answer_text": "I believe it is 44.5."}])

    result = await run_composition_subagent(
        context_package=_context_package([]),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.status == "succeeded"
    assert result.certainty.confidence == 0.3


@pytest.mark.asyncio
async def test_an_unresolved_failed_step_costs_the_answer_its_high_band(fake_llm_adapter_factory) -> None:
    """A step that never succeeded is a HOLE in the evidence, and prose written
    over a hole is not grounded -- however well-grounded everything around it is.

    CAUGHT LIVE (2026-07-16, ise_correctness `credits_remaining`), by the very
    fix this tests. Step `1e` deterministically summed credits earned (62.5,
    `official_record`). Step `1f` was to subtract it from the degree total and
    FAILED outright (`non_numeric_operand: subtract needs two numbers`, because
    `1d` handed it the string 'totalCreditsRequired: 155'). Composition then
    reported "Remaining credits needed: 92.5" anyway -- arithmetic it did
    in-model, standing in for the deterministic step that had just died. That is
    the F1 incident exactly; the model simply happened to be right this time.

    It shipped banded "high" because grounding was read off the SUCCEEDED
    entries only, so the one failure that forced the guess was the one thing
    invisible to the check.

    Distinct from a superseded retry (next test): `1f` had no successful
    attempt, so nothing filled the hole.
    """
    llm_adapter = fake_llm_adapter_factory(responses=[{"answer_text": "You have 92.5 credits remaining."}])

    result = await run_composition_subagent(
        context_package=_context_package(
            [
                _entry("1e", basis="official_record"),  # the credits sum that worked
                _entry("1f", basis="official_record", status="failed"),  # the subtraction that didn't
            ]
        ),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.certainty.confidence == 0.6, (
        "an answer that covered for a failed calculation with its own in-model arithmetic "
        "was banded as though every number in it had been computed"
    )


@pytest.mark.asyncio
async def test_a_superseded_failed_attempt_does_not_drag_down_a_grounded_answer(fake_llm_adapter_factory) -> None:
    """`PlanExecutionState` is append-only: a step retried after a replan leaves
    its failed first attempt in state forever. That attempt contributed nothing
    to the answer, so it must not cost the answer its grounding -- only
    `succeeded` entries are evidence."""
    llm_adapter = fake_llm_adapter_factory(responses=[{"answer_text": "You have completed 84.5 credits."}])

    result = await run_composition_subagent(
        context_package=_context_package(
            [
                _entry("s1", basis="llm_interpretation", status="failed"),  # superseded
                _entry("s1", basis="official_record"),  # the successful retry
            ]
        ),
        llm_adapter=llm_adapter,
        block_id="test-block",
    )

    assert result.certainty.confidence == 0.9
