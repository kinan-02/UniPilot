"""Unit tests for promotion readiness policy (Phase 24)."""

from __future__ import annotations

from app.agent.evaluation.readiness_policy import (
    default_promotion_candidates,
    evaluate_promotion_readiness,
)
from app.agent.evaluation.readiness_schemas import PromotionCandidate, ReadinessThresholds
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult
from app.agent.evaluation.suite_schemas import EvalSuiteManifest


def _case(case_id: str, tags: list[str] | None = None) -> EvalCase:
    return EvalCase(
        id=case_id,
        name=case_id,
        kind="course_question",
        user_message="hello",
        tags=list(tags or []),
    )


def _result(case_id: str, *, status: str = "passed", failures: list[str] | None = None) -> EvalCaseResult:
    return EvalCaseResult(case_id=case_id, name=case_id, status=status, failures=list(failures or []))


def _suite(suite_id: str, case_ids: list[str]) -> EvalSuiteManifest:
    return EvalSuiteManifest(
        id=suite_id,
        name=suite_id,
        purpose="core_regression",
        case_ids=case_ids,
        minimum_case_count=1,
    )


def test_not_ready_when_required_suite_missing() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["missing_suite"],
    )
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=[],
        suites=[],
        cases=[],
    )
    assert decision.level == "not_ready"
    assert any("missing_required_suite" in r for r in decision.blocking_reasons)


def test_not_ready_when_minimum_case_count_not_met() -> None:
    candidate = default_promotion_candidates()[0]
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1")]
    results = [_result("c1")]
    thresholds = ReadinessThresholds(min_candidate_case_count=5)
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=thresholds,
    )
    assert "min_candidate_case_count_not_met" in decision.blocking_reasons


def test_not_ready_when_pass_rate_below_threshold() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1", "c2"])]
    cases = [_case("c1"), _case("c2")]
    results = [_result("c1"), _result("c2", status="failed", failures=["x"])]
    thresholds = ReadinessThresholds(min_pass_rate=0.99, min_candidate_case_count=1)
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=thresholds,
    )
    assert "min_pass_rate_not_met" in decision.blocking_reasons


def test_not_ready_when_student_write_failures_exist() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1")]
    results = [EvalCaseResult(case_id="c1", name="c1", status="failed", safety_failures=["student_write_marker"])]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=ReadinessThresholds(min_candidate_case_count=1),
    )
    assert "student_write_failures_present" in decision.blocking_reasons


def test_not_ready_when_action_proposal_failures_exist() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1")]
    results = [EvalCaseResult(case_id="c1", name="c1", status="failed", safety_failures=["proposed_actions_present"])]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=ReadinessThresholds(min_candidate_case_count=1),
    )
    assert "action_proposal_failures_present" in decision.blocking_reasons


def test_not_ready_when_raw_payload_leaks_exist() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1")]
    results = [EvalCaseResult(case_id="c1", name="c1", status="failed", safety_failures=["raw_payload_leak"])]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=ReadinessThresholds(min_candidate_case_count=1),
    )
    assert "raw_payload_leaks_present" in decision.blocking_reasons


def test_not_ready_when_unexpected_promotions_exist() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="synthesis_text_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1")]
    results = [_result("c1", status="failed", failures=["synthesis_promotion_mismatch"])]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=ReadinessThresholds(min_candidate_case_count=1),
    )
    assert "unexpected_promotions_present" in decision.blocking_reasons


def test_ready_for_shadow_when_safety_passes_but_coverage_incomplete() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression", "write_safety"],
    )
    suites = [
        _suite("core_regression", ["c1", "c2"]),
        EvalSuiteManifest(
            id="write_safety",
            name="write",
            purpose="write_safety",
            case_ids=["c3"],
            minimum_case_count=3,
        ),
    ]
    cases = [_case("c1"), _case("c2"), _case("c3")]
    results = [_result("c1"), _result("c2"), _result("c3")]
    thresholds = ReadinessThresholds(min_candidate_case_count=1, min_pass_rate=0.5)
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=thresholds,
    )
    assert decision.level == "ready_for_shadow"


def test_ready_for_limited_promotion_when_all_thresholds_pass() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1", "c2", "c3"])]
    cases = [_case("c1"), _case("c2"), _case("c3")]
    results = [_result("c1"), _result("c2"), _result("c3")]
    thresholds = ReadinessThresholds(
        min_candidate_case_count=3,
        min_pass_rate=0.95,
    )
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=thresholds,
    )
    assert decision.level == "ready_for_limited_promotion"
    assert decision.passed is True


def test_ready_for_broader_promotion_only_with_diverse_coverage() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression", "write_safety"],
    )
    suites = [
        EvalSuiteManifest(id="core_regression", name="c", purpose="core_regression", case_ids=["c1"], minimum_case_count=1),
        EvalSuiteManifest(id="write_safety", name="w", purpose="write_safety", case_ids=["c2"], minimum_case_count=1),
    ]
    cases = [_case("c1"), _case("c2")]
    results = [_result("c1"), _result("c2")]
    thresholds = ReadinessThresholds(min_candidate_case_count=2, min_diverse_suite_count=2)
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=thresholds,
    )
    assert decision.level == "ready_for_broader_promotion"


def test_candidate_specific_suites_only() -> None:
    candidate = PromotionCandidate(
        id="test.candidate",
        type="workflow_promotion",
        name="Test",
        required_suites=["core_regression"],
    )
    suites = [_suite("core_regression", ["c1"])]
    cases = [_case("c1"), _case("other")]
    results = [_result("c1"), _result("other", status="failed")]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=results,
        suites=suites,
        cases=cases,
        thresholds=ReadinessThresholds(min_candidate_case_count=1),
    )
    assert decision.total_cases == 1
    assert decision.pass_rate == 1.0


def test_malformed_result_data_never_crashes() -> None:
    candidate = default_promotion_candidates()[0]
    decision = evaluate_promotion_readiness(
        candidate=candidate,
        eval_results=[],
        suites=[],
        cases=[],
    )
    assert decision.level == "not_ready"
