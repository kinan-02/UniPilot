"""Unit tests for agent eval scoring rules."""

from __future__ import annotations

from app.agent.evaluation.agent_eval_scorer import AgentTurnResult, score_agent_turn


def test_score_passes_when_expectations_met():
    result = AgentTurnResult(
        text="You need 40 more credits to graduate.",
        events=[
            {"type": "structured_output", "block": {"type": "RequirementSummaryBlock", "data": {}}},
        ],
        latency_ms=1200.0,
    )
    outcome = score_agent_turn(
        message="What am I missing to graduate?",
        result=result,
        expect={
            "intent": "graduation_progress_check",
            "textContainsAny": ["credit", "graduat"],
            "blockTypesAny": ["RequirementSummaryBlock"],
        },
    )
    assert outcome.passed
    assert not outcome.failures


def test_score_fails_on_wrong_intent():
    outcome = score_agent_turn(
        message="Hello there",
        result=AgentTurnResult(text="Hi"),
        expect={"intent": "graduation_progress_check"},
    )
    assert not outcome.passed
    assert any("intent" in failure for failure in outcome.failures)


def test_score_fails_on_run_failed():
    outcome = score_agent_turn(
        message="What am I missing to graduate?",
        result=AgentTurnResult(text="", run_failed=True, run_error="boom"),
        expect={"intent": "graduation_progress_check", "noRunFailed": True},
    )
    assert not outcome.passed
    assert any("run.failed" in failure for failure in outcome.failures)


def test_score_fails_on_forbidden_text():
    outcome = score_agent_turn(
        message="Explain electives",
        result=AgentTurnResult(text="This workflow is not fully available yet."),
        expect={
            "intent": "requirement_explanation",
            "textNotContains": ["not fully available"],
        },
    )
    assert not outcome.passed
    assert any("forbidden" in failure for failure in outcome.failures)
