"""Unit tests for eval suite schemas (Phase 24)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.readiness_schemas import (
    PromotionCandidate,
    PromotionReadinessDecision,
    ReadinessThresholds,
)
from app.agent.evaluation.suite_schemas import EvalSuiteManifest


def test_eval_suite_manifest_parses() -> None:
    suite = EvalSuiteManifest(
        id="core_regression",
        name="Core",
        purpose="core_regression",
        case_ids=["c1"],
    )
    assert suite.minimum_case_count == 1


def test_promotion_candidate_parses() -> None:
    candidate = PromotionCandidate(
        id="workflow_promotion.graduation_progress_workflow",
        type="workflow_promotion",
        name="Graduation workflow",
        required_suites=["core_regression"],
    )
    assert candidate.type == "workflow_promotion"


def test_readiness_thresholds_parses() -> None:
    thresholds = ReadinessThresholds(min_pass_rate=0.9)
    assert thresholds.require_zero_unsafe_failures is True


def test_promotion_readiness_decision_parses() -> None:
    decision = PromotionReadinessDecision(
        candidate_id="c1",
        level="not_ready",
        passed=False,
        summary="not ready",
    )
    assert decision.level == "not_ready"


def test_defaults_are_safe() -> None:
    thresholds = ReadinessThresholds()
    assert thresholds.require_zero_action_proposal_failures is True


def test_suite_rejects_forbidden_chain_of_thought_field() -> None:
    with pytest.raises(ValueError, match="forbidden_field"):
        EvalSuiteManifest.model_validate(
            {
                "id": "bad",
                "name": "bad",
                "purpose": "core_regression",
                "chain_of_thought": "secret",
            }
        )
