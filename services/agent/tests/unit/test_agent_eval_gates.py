"""Unit tests for offline eval gates evaluator (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.gates_eval import build_observed_from_case, evaluate_case_result
from app.agent.evaluation.replay_schemas import EvalCase, EvalExpectedOutcome


def _case(**kwargs: object) -> EvalCase:
    base = {
        "id": "c1",
        "name": "Case",
        "kind": "course_question",
        "user_message": "hello",
    }
    base.update(kwargs)
    return EvalCase.model_validate(base)


def test_expected_intent_passes() -> None:
    case = _case(
        compact_context={"intent": "course_question"},
        expected={"expected_intent": "course_question"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_wrong_intent_fails() -> None:
    case = _case(expected={"expected_intent": "graduation_progress"})
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "failed"
    assert "expected_intent_mismatch" in result.failures


def test_prerequisite_check_alias_matches_course_question_expectation() -> None:
    case = _case(
        compact_context={"intent": "course_question"},
        expected={"expected_intent": "course_question"},
        retrieval_metadata={"taskUnderstanding": {"primaryIntent": "prerequisite_check"}},
    )
    observed = build_observed_from_case(case)
    result = evaluate_case_result(case=case, observed=observed)
    assert result.status == "passed"


def test_semester_plan_generation_alias_matches_semester_planning_expectation() -> None:
    case = _case(
        compact_context={"intent": "semester_plan_generation"},
        expected={"expected_intent": "semester_planning"},
        retrieval_metadata={"taskUnderstanding": {"primaryIntent": "semester_plan_generation"}},
    )
    observed = build_observed_from_case(case)
    result = evaluate_case_result(case=case, observed=observed)
    assert result.status == "passed"


def test_expected_workflow_passes() -> None:
    case = _case(
        compact_context={"workflow": "course_question_workflow"},
        expected={"expected_workflow": "course_question_workflow"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_wrong_workflow_fails() -> None:
    case = _case(
        compact_context={"workflow": "other_workflow"},
        expected={"expected_workflow": "course_question_workflow"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "expected_workflow_mismatch" in result.failures


def test_dynamic_spec_validation_outcome_checked() -> None:
    case = _case(
        retrieval_metadata={
            "plannerDynamicAgents": {"specCount": 1, "agents": [{"status": "validated"}]}
        },
        expected={"expected_dynamic_spec_statuses": ["validated"]},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_monitor_signals_checked() -> None:
    case = _case(
        retrieval_metadata={"monitorDiagnostics": {"signals": [{"kind": "unsafe_output"}]}},
        expected={"expected_monitor_signals": ["unsafe_output"]},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_clarification_action_checked() -> None:
    case = _case(
        retrieval_metadata={"clarificationDiagnostics": {"status": "ask"}},
        expected={"expected_clarification_action": "ask"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_plan_repair_mode_checked() -> None:
    case = _case(
        retrieval_metadata={"planRepairDiagnostics": {"modeUsed": "repair"}},
        expected={"expected_plan_repair_mode": "repair"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_synthesis_status_checked() -> None:
    case = _case(
        retrieval_metadata={"synthesisDiagnostics": {"status": "candidate_ready"}},
        expected={"expected_synthesis_status": "candidate_ready"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_synthesis_promotion_outcome_checked() -> None:
    case = _case(
        retrieval_metadata={"synthesisPromotion": {"promoted": True, "status": "promoted"}},
        expected={"expected_synthesis_promotion": "promoted"},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert result.status == "passed"


def test_forbidden_reason_code_fails() -> None:
    case = _case(
        retrieval_metadata={"synthesisPromotion": {"reasons": [{"code": "unsafe"}]}},
        expected={"forbidden_reason_codes": ["unsafe"]},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "forbidden_reason_code_present" in result.failures


def test_missing_required_reason_code_fails() -> None:
    case = _case(
        retrieval_metadata={"synthesisPromotion": {"reasons": [{"code": "other"}]}},
        expected={"expected_required_reason_codes": ["needed_code"]},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "missing_required_reason_code" in result.failures


def test_proposed_action_presence_fails() -> None:
    case = _case(live_response_summary={"proposedActionCount": 2})
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "proposed_actions_present" in result.failures


def test_student_write_marker_fails() -> None:
    case = _case(live_response_summary={"textPreview": "I saved your plan."})
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "student_write_marker" in result.failures


def test_oracle_contradiction_fails() -> None:
    case = _case(
        synthetic_world={
            "degree": {"totalRequiredCredits": 10, "mandatoryCourses": []},
            "courses": {"A": {"credits": 3}},
            "student": {"completedCourses": ["A"]},
        },
        expected=EvalExpectedOutcome(expected_oracle_facts={"completedCredits": 99}),
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert any(f.startswith("oracle_mismatch:") for f in result.failures)


def test_forbidden_claim_fails() -> None:
    case = _case(
        live_response_summary={"textPreview": "You are enrolled in course B."},
        expected={"forbidden_claims": ["you are enrolled"]},
    )
    result = evaluate_case_result(case=case, observed=build_observed_from_case(case))
    assert "forbidden_claim_present" in result.failures
