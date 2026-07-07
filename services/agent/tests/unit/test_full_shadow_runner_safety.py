"""Unit tests for full shadow runner safety (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.full_shadow_reporting import build_full_shadow_eval_report
from app.agent.evaluation.full_shadow_runner import run_full_llm_shadow_eval_case
from app.agent.evaluation.replay_schemas import EvalCase, MockReasoningOutput
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload


def _case() -> EvalCase:
    return EvalCase(
        id="full_shadow_case",
        name="Full shadow case",
        kind="course_question",
        user_message="What are prerequisites for course B?",
        compact_context={"intent": "course_question", "workflow": "course_question_workflow"},
        retrieval_metadata={
            "synthesisDiagnostics": {"status": "candidate_ready", "safeToShow": True, "confidence": 0.9},
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        live_response_summary={"textPreview": "Course B requires course A.", "blockCount": 1},
        mock_reasoning_outputs=[
            MockReasoningOutput(
                contract_name="intent_classifier_v1",
                output={"decision_summary": "course question", "confidence": 0.9, "primary_intent": "course_question"},
            )
        ],
        expected={"expected_intent": "course_question", "expected_workflow": "course_question_workflow"},
        tags=["real_world_like"],
    )


@pytest.mark.asyncio
async def test_full_llm_shadow_requires_allow_real_llm() -> None:
    result = await run_full_llm_shadow_eval_case(_case(), allow_real_llm=False, max_reasoning_calls=5)
    assert result.status == "error"
    assert "full_llm_shadow_requires_allow_real_llm" in result.failures


@pytest.mark.asyncio
async def test_side_effect_violation_fails_case(monkeypatch) -> None:
    from app.agent.evaluation.side_effect_firewall import EvalSideEffectFirewall

    firewall = EvalSideEffectFirewall()
    firewall._record("student_profile_write", "test")  # noqa: SLF001

    async def _fake_pipeline(*_args, **_kwargs):
        from app.agent.evaluation.llm_trace_summary import TracedReasoningBlockRunner
        from app.agent.evaluation.fake_reasoning import FakeReasoningBlockRunner

        traced = TracedReasoningBlockRunner(FakeReasoningBlockRunner([]))
        return {}, traced

    monkeypatch.setattr("app.agent.evaluation.full_shadow_runner._run_lab_pipeline", _fake_pipeline)

    result = await run_full_llm_shadow_eval_case(
        _case(),
        allow_real_llm=True,
        max_reasoning_calls=5,
        firewall=firewall,
    )
    assert result.status == "failed"
    assert "side_effect_violation" in result.failures


@pytest.mark.asyncio
async def test_observed_metadata_is_sanitized() -> None:
    result = await run_full_llm_shadow_eval_case(_case(), allow_real_llm=True, max_reasoning_calls=5)
    assert_no_forbidden_eval_payload(result.model_dump())


@pytest.mark.asyncio
async def test_no_candidate_text_in_report() -> None:
    result = await run_full_llm_shadow_eval_case(_case(), allow_real_llm=True, max_reasoning_calls=5)
    report = build_full_shadow_eval_report([result], allow_real_llm=True)
    serialized = str(report).lower()
    assert "course b requires course a" not in serialized


@pytest.mark.asyncio
async def test_no_prompt_or_raw_output_in_report() -> None:
    result = await run_full_llm_shadow_eval_case(_case(), allow_real_llm=True, max_reasoning_calls=5)
    report = build_full_shadow_eval_report([result], allow_real_llm=True)
    assert "raw_prompt" not in report
    assert "chain_of_thought" not in str(report)
