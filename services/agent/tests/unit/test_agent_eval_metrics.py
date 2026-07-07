"""Unit tests for offline eval metrics (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.metrics import compute_eval_run_summary
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult, EvalExpectedOutcome


def test_pass_rate_computed() -> None:
    results = [
        EvalCaseResult(case_id="a", name="A", status="passed"),
        EvalCaseResult(case_id="b", name="B", status="failed", failures=["x"]),
    ]
    summary = compute_eval_run_summary(results)
    assert summary.total_cases == 2
    assert summary.passed_cases == 1
    assert summary.pass_rate == 0.5


def test_intent_accuracy_computed() -> None:
    cases = [
        EvalCase(
            id="a",
            name="A",
            kind="course_question",
            user_message="x",
            expected=EvalExpectedOutcome(expected_intent="course_question"),
        )
    ]
    results = [EvalCaseResult(case_id="a", name="A", status="passed")]
    summary = compute_eval_run_summary(results, cases=cases)
    assert summary.intent_accuracy == 1.0


def test_workflow_accuracy_computed() -> None:
    cases = [
        EvalCase(
            id="a",
            name="A",
            kind="course_question",
            user_message="x",
            expected=EvalExpectedOutcome(expected_workflow="course_question_workflow"),
        )
    ]
    results = [
        EvalCaseResult(
            case_id="a",
            name="A",
            status="failed",
            failures=["expected_workflow_mismatch"],
        )
    ]
    summary = compute_eval_run_summary(results, cases=cases)
    assert summary.workflow_accuracy == 0.0


def test_synthesis_promotion_counts_computed() -> None:
    results = [
        EvalCaseResult(
            case_id="a",
            name="A",
            status="passed",
            actual_synthesis_status="candidate_ready",
            actual_synthesis_promotion="promoted",
        ),
        EvalCaseResult(
            case_id="b",
            name="B",
            status="failed",
            actual_synthesis_status="unsafe",
            actual_synthesis_promotion="blocked",
        ),
    ]
    summary = compute_eval_run_summary(results)
    assert summary.synthesis_candidates == 2
    assert summary.synthesis_promotions == 1
    assert summary.synthesis_blocks == 1


def test_unsafe_block_counts_computed() -> None:
    results = [
        EvalCaseResult(
            case_id="a",
            name="A",
            status="failed",
            actual_synthesis_status="unsafe",
            actual_synthesis_promotion="blocked",
        )
    ]
    summary = compute_eval_run_summary(results)
    assert summary.unsafe_cases_blocked == 1
