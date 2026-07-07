"""Unit tests for offline eval schemas (Phase 23)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.replay_schemas import (
    EvalCase,
    EvalCaseResult,
    EvalExpectedOutcome,
    EvalRunSummary,
    MockReasoningOutput,
)


def test_eval_case_parses_minimal() -> None:
    case = EvalCase(
        id="c1",
        name="Case 1",
        kind="course_question",
        user_message="hello",
    )
    assert case.id == "c1"
    assert case.expected.must_not_create_proposed_actions is True


def test_eval_expected_outcome_defaults_are_safe() -> None:
    outcome = EvalExpectedOutcome()
    assert outcome.must_not_write_student_data is True
    assert outcome.must_not_change_blocks is True
    assert outcome.expected_synthesis_promotion == "not_applicable"


def test_mock_reasoning_output_parses() -> None:
    mock = MockReasoningOutput(contract_name="planner", output={"status": "ok"})
    assert mock.contract_name == "planner"


def test_eval_case_result_parses() -> None:
    result = EvalCaseResult(case_id="c1", name="Case 1", status="passed")
    assert result.status == "passed"


def test_eval_run_summary_parses() -> None:
    summary = EvalRunSummary(
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        errored_cases=0,
        pass_rate=1.0,
    )
    assert summary.pass_rate == 1.0


def test_eval_case_rejects_forbidden_chain_of_thought_field() -> None:
    with pytest.raises(ValueError, match="forbidden_field"):
        EvalCase.model_validate(
            {
                "id": "bad",
                "name": "bad",
                "kind": "course_question",
                "user_message": "x",
                "chain_of_thought": "secret",
            }
        )
