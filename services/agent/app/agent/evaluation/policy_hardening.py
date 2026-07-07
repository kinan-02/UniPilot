"""Offline policy hardening recommendations (Phase 24)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.readiness_schemas import PromotionReadinessDecision
from app.agent.evaluation.replay_schemas import EvalCaseResult
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload

_ALLOWED_RECOMMENDATIONS = frozenset(
    {
        "keep_disabled",
        "keep_shadow_only",
        "add_more_eval_cases",
        "tighten_candidate_safety",
        "tighten_monitor_blocking",
        "expand_fixture_coverage",
        "eligible_for_limited_promotion_review",
    }
)


def build_policy_hardening_recommendations(
    *,
    eval_results: list[EvalCaseResult],
    readiness_decisions: list[PromotionReadinessDecision],
) -> list[dict[str, Any]]:
    """Compact, non-authoritative recommendations from eval + readiness results."""
    recommendations: list[dict[str, Any]] = []

    total_safety_failures = sum(
        1 for item in eval_results if item.safety_failures or item.status == "failed"
    )
    raw_leaks = sum(1 for item in eval_results if "raw_payload_leak" in item.safety_failures)

    for decision in sorted(readiness_decisions, key=lambda item: item.candidate_id):
        rec = _recommend_for_candidate(decision, raw_leaks=raw_leaks)
        if rec:
            recommendations.append(rec)

    if total_safety_failures and not any(
        item.get("recommendation") == "keep_disabled" for item in recommendations
    ):
        recommendations.append(
            {
                "target": "global",
                "recommendation": "tighten_candidate_safety",
                "reason": "safety_failures_detected_in_eval_run",
            }
        )

    sanitized_items: list[dict[str, Any]] = []
    for item in recommendations:
        recommendation = str(item.get("recommendation") or "")
        if recommendation not in _ALLOWED_RECOMMENDATIONS:
            continue
        cleaned = {
            "target": str(item.get("target") or ""),
            "recommendation": recommendation,
            "reason": str(item.get("reason") or "")[:200],
        }
        sanitized_items.append(cleaned)

    payload = {"recommendations": sanitized_items}
    sanitized = sanitize_eval_payload(payload, strict=False)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else payload)
    return sanitized_items


def _recommend_for_candidate(
    decision: PromotionReadinessDecision,
    *,
    raw_leaks: int,
) -> dict[str, Any] | None:
    target = decision.candidate_id

    if raw_leaks > 0 or int(decision.metrics.get("rawPayloadLeaks") or 0) > 0:
        return {
            "target": target,
            "recommendation": "keep_disabled",
            "reason": "raw_payload_leak_detected",
        }

    if int(decision.metrics.get("studentWriteFailures") or 0) > 0:
        return {
            "target": target,
            "recommendation": "keep_disabled",
            "reason": "student_write_failures_present",
        }

    if int(decision.metrics.get("unexpectedPromotions") or 0) > 0:
        return {
            "target": target,
            "recommendation": "tighten_candidate_safety",
            "reason": "promotion_false_positive_detected",
        }

    if "min_unsafe_block_rate_not_met" in decision.blocking_reasons:
        return {
            "target": target,
            "recommendation": "tighten_monitor_blocking",
            "reason": "unsafe_case_coverage_too_low",
        }

    if any(reason.startswith("suite_minimum_not_met") for reason in decision.blocking_reasons):
        return {
            "target": target,
            "recommendation": "add_more_eval_cases",
            "reason": "suite_coverage_too_low",
        }

    if "min_candidate_case_count_not_met" in decision.blocking_reasons:
        return {
            "target": target,
            "recommendation": "expand_fixture_coverage",
            "reason": "candidate_case_count_too_low",
        }

    if decision.level == "ready_for_limited_promotion":
        return {
            "target": target,
            "recommendation": "eligible_for_limited_promotion_review",
            "reason": "all_required_thresholds_passed",
        }

    if decision.level == "ready_for_broader_promotion":
        return {
            "target": target,
            "recommendation": "eligible_for_limited_promotion_review",
            "reason": "diverse_coverage_thresholds_passed",
        }

    if decision.level == "ready_for_shadow":
        return {
            "target": target,
            "recommendation": "keep_shadow_only",
            "reason": "safety_passed_promotion_thresholds_incomplete",
        }

    if decision.level == "not_ready":
        return {
            "target": target,
            "recommendation": "keep_disabled",
            "reason": "blocking_thresholds_failed",
        }

    return None
