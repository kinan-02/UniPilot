"""Unit tests for readiness scorecard (Phase 24)."""

from __future__ import annotations

from app.agent.evaluation.readiness_policy import default_promotion_candidates
from app.agent.evaluation.readiness_scorecard import build_readiness_scorecard
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult
from app.agent.evaluation.suite_schemas import EvalSuiteManifest


def _minimal_inputs() -> tuple[list[EvalCaseResult], list[EvalSuiteManifest], list[EvalCase]]:
    cases = [
        EvalCase(id="c1", name="c1", kind="course_question", user_message="x"),
        EvalCase(id="c2", name="c2", kind="course_question", user_message="y"),
        EvalCase(id="c3", name="c3", kind="course_question", user_message="z"),
    ]
    suites = [
        EvalSuiteManifest(
            id="core_regression",
            name="core",
            purpose="core_regression",
            case_ids=["c1", "c2", "c3"],
            minimum_case_count=1,
        )
    ]
    results = [
        EvalCaseResult(case_id="c1", name="c1", status="passed"),
        EvalCaseResult(case_id="c2", name="c2", status="passed"),
        EvalCaseResult(case_id="c3", name="c3", status="passed"),
    ]
    return results, suites, cases


def test_scorecard_includes_all_candidates() -> None:
    results, suites, cases = _minimal_inputs()
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    assert len(scorecard["candidates"]) == len(default_promotion_candidates())


def test_summary_counts_levels() -> None:
    results, suites, cases = _minimal_inputs()
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    summary = scorecard["summary"]
    assert summary["candidateCount"] == len(default_promotion_candidates())
    assert summary["notReady"] + summary["readyForShadow"] + summary["readyForLimitedPromotion"] + summary["readyForBroaderPromotion"] == summary["candidateCount"]


def test_blocking_reasons_included() -> None:
    results, suites, cases = _minimal_inputs()
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    assert all("blockingReasons" in item for item in scorecard["candidates"])


def test_metrics_included() -> None:
    results, suites, cases = _minimal_inputs()
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    assert all("metrics" in item for item in scorecard["candidates"])


def test_raw_case_payloads_omitted() -> None:
    results, suites, cases = _minimal_inputs()
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    text = str(scorecard)
    assert "user_message" not in text
    assert "raw_context" not in text


def test_deterministic_ordering() -> None:
    results, suites, cases = _minimal_inputs()
    first = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    second = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    assert [c["candidateId"] for c in first["candidates"]] == [c["candidateId"] for c in second["candidates"]]
