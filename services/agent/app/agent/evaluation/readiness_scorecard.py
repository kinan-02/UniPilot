"""Build promotion readiness scorecards (Phase 24)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.readiness_policy import (
    default_promotion_candidates,
    evaluate_promotion_readiness,
    resolve_suite_case_ids,
)
from app.agent.evaluation.readiness_schemas import (
    PromotionCandidate,
    PromotionReadinessDecision,
    ReadinessThresholds,
)
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload
from app.agent.evaluation.suite_schemas import EvalSuiteManifest


def build_readiness_scorecard(
    *,
    eval_results: list[EvalCaseResult],
    suites: list[EvalSuiteManifest],
    cases: list[EvalCase],
    candidates: list[PromotionCandidate] | None = None,
    thresholds: ReadinessThresholds | None = None,
) -> dict[str, Any]:
    """Build a compact readiness scorecard from eval results. No raw case payloads."""
    thresholds = thresholds or ReadinessThresholds()
    candidates = candidates or default_promotion_candidates()

    decisions: list[PromotionReadinessDecision] = []
    for candidate in sorted(candidates, key=lambda item: item.id):
        decisions.append(
            evaluate_promotion_readiness(
                candidate=candidate,
                eval_results=eval_results,
                suites=suites,
                cases=cases,
                thresholds=thresholds,
            )
        )

    level_counts = {
        "notReady": sum(1 for d in decisions if d.level == "not_ready"),
        "readyForShadow": sum(1 for d in decisions if d.level == "ready_for_shadow"),
        "readyForLimitedPromotion": sum(
            1 for d in decisions if d.level == "ready_for_limited_promotion"
        ),
        "readyForBroaderPromotion": sum(
            1 for d in decisions if d.level == "ready_for_broader_promotion"
        ),
    }

    suite_coverage = []
    for suite in sorted(suites, key=lambda item: item.id):
        resolved = resolve_suite_case_ids(suite, cases)
        suite_coverage.append(
            {
                "suiteId": suite.id,
                "purpose": suite.purpose,
                "caseCount": len(resolved),
                "minimumCaseCount": suite.minimum_case_count,
                "meetsMinimum": len(resolved) >= suite.minimum_case_count,
            }
        )

    safety_failures = {
        "studentWriteFailures": sum(
            int(d.metrics.get("studentWriteFailures") or 0) for d in decisions
        ),
        "actionProposalFailures": sum(
            int(d.metrics.get("actionProposalFailures") or 0) for d in decisions
        ),
        "rawPayloadLeaks": sum(int(d.metrics.get("rawPayloadLeaks") or 0) for d in decisions),
        "unexpectedPromotions": sum(
            int(d.metrics.get("unexpectedPromotions") or 0) for d in decisions
        ),
    }

    scorecard: dict[str, Any] = {
        "summary": {
            "candidateCount": len(decisions),
            **level_counts,
            "readinessPassed": sum(1 for d in decisions if d.passed),
        },
        "thresholds": thresholds.model_dump(),
        "suiteCoverage": suite_coverage,
        "safetyFailures": safety_failures,
        "candidates": [
            {
                "candidateId": decision.candidate_id,
                "level": decision.level,
                "passed": decision.passed,
                "passRate": decision.pass_rate,
                "totalCases": decision.total_cases,
                "passedCases": decision.passed_cases,
                "failedCases": decision.failed_cases,
                "evaluatedSuiteIds": decision.evaluated_suite_ids,
                "blockingReasons": decision.blocking_reasons[:20],
                "warnings": decision.warnings[:10],
                "metrics": decision.metrics,
            }
            for decision in decisions
        ],
    }

    sanitized = sanitize_eval_payload(scorecard, strict=False)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else scorecard)
    return sanitized if isinstance(sanitized, dict) else scorecard
