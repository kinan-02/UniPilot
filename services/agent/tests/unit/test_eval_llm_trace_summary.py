"""Unit tests for LLM trace summary (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.fake_reasoning import FakeReasoningBlockRunner
from app.agent.evaluation.llm_trace_summary import (
    ReasoningContractCallSummary,
    TracedReasoningBlockRunner,
    sanitize_trace_string_list,
    summarize_contract_calls,
)
from app.agent.evaluation.replay_schemas import MockReasoningOutput
from app.agent.reasoning.schemas import ReasoningBlockInput


async def _run_trace() -> TracedReasoningBlockRunner:
    inner = FakeReasoningBlockRunner(
        [MockReasoningOutput(contract_name="intent_classifier_v1", output={"decision_summary": "ok", "confidence": 0.9})]
    )
    traced = TracedReasoningBlockRunner(inner)
    await traced.run(
        ReasoningBlockInput(
            block_id="t1",
            agent_name="eval",
            objective="classify",
            output_schema_name="intent_classifier_v1",
            output_schema={"type": "object"},
            prompt_contract_name="intent_classifier_v1",
        )
    )
    return traced


@pytest.mark.asyncio
async def test_summarizes_contract_name() -> None:
    traced = await _run_trace()
    assert traced.summaries[0].contract_name == "intent_classifier_v1"


@pytest.mark.asyncio
async def test_summarizes_status() -> None:
    traced = await _run_trace()
    assert traced.summaries[0].status == "completed"


@pytest.mark.asyncio
async def test_counts_calls_by_contract() -> None:
    traced = await _run_trace()
    summary = summarize_contract_calls(traced.summaries)
    assert summary["contractCallCounts"]["intent_classifier_v1"] == 1


@pytest.mark.asyncio
async def test_omits_prompt_text() -> None:
    summary = summarize_contract_calls(
        [ReasoningContractCallSummary(contract_name="intent_classifier_v1", status="completed")]
    )
    assert "prompt" not in str(summary).lower()


@pytest.mark.asyncio
async def test_omits_raw_model_output() -> None:
    traced = await _run_trace()
    payload = summarize_contract_calls(traced.summaries)
    assert "raw_response" not in payload
    assert "raw_output" not in str(payload)


@pytest.mark.asyncio
async def test_omits_raw_context() -> None:
    summary = summarize_contract_calls(
        [ReasoningContractCallSummary(contract_name="planner_v1", status="completed", output_schema_name="PlannerOutput")]
    )
    call = summary.get("calls", [{}])[0]
    assert "task_context" not in call
    assert call.get("schemaValid") is False


def test_records_schema_valid_and_validation_notes() -> None:
    summary = summarize_contract_calls(
        [
            ReasoningContractCallSummary(
                contract_name="task_understanding_v1",
                status="fallback",
                reasoning_status="completed",
                schema_valid=False,
                validation_retry_count=2,
                output_schema_name="task_understanding_output_v1",
                validation_notes=["schema_validation_failed", "missing field primary_intent"],
                warnings=["task_understanding_llm_unavailable_or_failed"],
            )
        ]
    )
    call = summary["calls"][0]
    assert call["schemaValid"] is False
    assert call["reasoningStatus"] == "completed"
    assert call["validationNotes"]
    assert summary["schemaValidationFailures"]["task_understanding_v1"] == 1


def test_sanitize_trace_string_list_strips_forbidden_tokens() -> None:
    notes = sanitize_trace_string_list(["ok note", "raw_prompt leaked", "schema failed"])
    assert "raw_prompt leaked" not in notes
    assert "ok note" in notes
