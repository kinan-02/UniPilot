"""Integration tests ensuring full shadow replay does not call real LLMs (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.replay_runner import run_eval_case, run_eval_cases
from app.agent.evaluation.replay_schemas import EvalCase, MockReasoningOutput


def _case() -> EvalCase:
    return EvalCase(
        id="no_real_llm_case",
        name="No real LLM",
        kind="course_question",
        user_message="What are prerequisites?",
        compact_context={"intent": "course_question", "workflow": "course_question_workflow"},
        retrieval_metadata={
            "taskUnderstanding": {"primaryIntent": "course_question"},
            "plannerDiagnostics": {"workflowName": "course_question_workflow"},
            "synthesisDiagnostics": {"status": "candidate_ready", "safeToShow": True, "confidence": 0.9},
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        live_response_summary={"textPreview": "Preview answer.", "blockCount": 1},
        mock_reasoning_outputs=[
            MockReasoningOutput(
                contract_name="intent_classifier_v1",
                output={"decision_summary": "ok", "confidence": 0.9, "primary_intent": "course_question"},
            )
        ],
        expected={"expected_intent": "course_question"},
        tags=["real_world_like"],
    )


@pytest.mark.asyncio
async def test_gates_only_still_never_calls_real_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("real_llm_called")),
    )
    result = await run_eval_case(_case(), mode="gates_only", allow_real_llm=False)
    assert result.status in {"passed", "failed"}


@pytest.mark.asyncio
async def test_full_shadow_without_allow_real_llm_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("real_llm_called")),
    )
    result = await run_eval_case(_case(), mode="full_llm_shadow_replay", allow_real_llm=False)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_full_shadow_with_mock_reasoning_never_calls_openai(monkeypatch) -> None:
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("real_llm_called")),
    )
    result = await run_eval_case(_case(), mode="full_llm_shadow_replay", allow_real_llm=True)
    assert result.status in {"passed", "failed", "error"}
    assert "real_llm_called" not in str(result.failures)


@pytest.mark.asyncio
async def test_side_effect_firewall_enabled_in_full_shadow() -> None:
    results = await run_eval_cases(
        [_case()],
        mode="full_llm_shadow_replay",
        allow_real_llm=True,
        max_cases=1,
    )
    assert results
    assert results[0].full_shadow.get("realLlmUsed") is True
