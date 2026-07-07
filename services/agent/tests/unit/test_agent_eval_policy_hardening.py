"""Unit tests for policy hardening recommendations (Phase 24)."""

from __future__ import annotations

from app.agent.evaluation.policy_hardening import build_policy_hardening_recommendations
from app.agent.evaluation.readiness_schemas import PromotionReadinessDecision
from app.agent.evaluation.replay_schemas import EvalCaseResult


def test_unsafe_failure_recommends_keep_disabled() -> None:
    results = [EvalCaseResult(case_id="c1", name="c1", status="failed", safety_failures=["raw_payload_leak"])]
    decisions = [
        PromotionReadinessDecision(
            candidate_id="synthesis_text_promotion.course_question_workflow",
            level="not_ready",
            passed=False,
            summary="not ready",
            metrics={"rawPayloadLeaks": 1},
        )
    ]
    recs = build_policy_hardening_recommendations(eval_results=results, readiness_decisions=decisions)
    assert any(item["recommendation"] == "keep_disabled" for item in recs)


def test_low_coverage_recommends_add_more_eval_cases() -> None:
    decisions = [
        PromotionReadinessDecision(
            candidate_id="test",
            level="ready_for_shadow",
            passed=False,
            summary="shadow",
            blocking_reasons=["suite_minimum_not_met:core_regression"],
        )
    ]
    recs = build_policy_hardening_recommendations(eval_results=[], readiness_decisions=decisions)
    assert any(item["recommendation"] == "add_more_eval_cases" for item in recs)


def test_promotion_false_positive_recommends_tighten_candidate_safety() -> None:
    decisions = [
        PromotionReadinessDecision(
            candidate_id="test",
            level="not_ready",
            passed=False,
            summary="not ready",
            metrics={"unexpectedPromotions": 1},
        )
    ]
    recs = build_policy_hardening_recommendations(eval_results=[], readiness_decisions=decisions)
    assert any(item["recommendation"] == "tighten_candidate_safety" for item in recs)


def test_all_thresholds_pass_recommends_eligible_for_limited_promotion_review() -> None:
    decisions = [
        PromotionReadinessDecision(
            candidate_id="test",
            level="ready_for_limited_promotion",
            passed=True,
            summary="ready",
        )
    ]
    recs = build_policy_hardening_recommendations(eval_results=[], readiness_decisions=decisions)
    assert any(item["recommendation"] == "eligible_for_limited_promotion_review" for item in recs)


def test_recommendations_are_compact_and_sanitized() -> None:
    decisions = [
        PromotionReadinessDecision(
            candidate_id="test",
            level="ready_for_shadow",
            passed=False,
            summary="shadow",
        )
    ]
    recs = build_policy_hardening_recommendations(eval_results=[], readiness_decisions=decisions)
    text = str(recs)
    assert "raw_context" not in text
    assert all(set(item.keys()) <= {"target", "recommendation", "reason"} for item in recs)
