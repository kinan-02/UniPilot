"""Tests for clarification action normalization in eval gates."""

from __future__ import annotations

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.gates_eval import build_observed_from_case, evaluate_case_result
from app.agent.evaluation.replay_schemas import EvalExpectedOutcome

_FIXTURE = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "fixtures"
    / "eval_cases_real_world_like"
    / "real_world_like_next_semester_missing_prefs.json"
)


def test_guardrail_fixture_passes_with_ask_user_action() -> None:
    case = load_eval_cases(_FIXTURE, strict=True)[0]
    observed = build_observed_from_case(
        case,
        replay_observed={
            "clarificationDiagnostics": {
                "action": "ask_user",
                "status": "question_ready",
                "questions": [{"ambiguityType": "preference", "consequence": "medium"}],
            }
        },
    )
    result = evaluate_case_result(case=case, observed=observed)
    assert "clarification_action_mismatch" not in result.failures


def test_question_ready_status_maps_to_ask_user() -> None:
    case = load_eval_cases(_FIXTURE, strict=True)[0]
    observed = build_observed_from_case(
        case,
        replay_observed={
            "clarificationDiagnostics": {
                "status": "question_ready",
                "questions": [{"ambiguityType": "preference", "consequence": "medium"}],
            }
        },
    )
    assert observed["clarification_action"] == "ask_user"

    case_ask = case.model_copy(
        update={"expected": EvalExpectedOutcome(expected_clarification_action="ask")}
    )
    result = evaluate_case_result(case=case_ask, observed=observed)
    assert "clarification_action_mismatch" not in result.failures
