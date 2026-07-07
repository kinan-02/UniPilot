"""Unit tests for readiness reporting (Phase 24)."""

from __future__ import annotations

from app.agent.evaluation.readiness_reporting import render_readiness_markdown_report


def _sample_scorecard() -> dict:
    return {
        "summary": {
            "candidateCount": 2,
            "readyForLimitedPromotion": 1,
            "readyForBroaderPromotion": 0,
            "readyForShadow": 1,
            "notReady": 0,
        },
        "suiteCoverage": [
            {"suiteId": "core_regression", "purpose": "core_regression", "caseCount": 5, "minimumCaseCount": 3, "meetsMinimum": True}
        ],
        "safetyFailures": {"studentWriteFailures": 0, "actionProposalFailures": 0, "rawPayloadLeaks": 0, "unexpectedPromotions": 0},
        "candidates": [
            {
                "candidateId": "test.candidate",
                "level": "ready_for_limited_promotion",
                "passRate": 1.0,
                "passedCases": 5,
                "totalCases": 5,
                "blockingReasons": [],
            }
        ],
        "recommendations": [
            {"target": "test.candidate", "recommendation": "eligible_for_limited_promotion_review", "reason": "all thresholds passed"}
        ],
    }


def test_markdown_report_renders() -> None:
    md = render_readiness_markdown_report(_sample_scorecard())
    assert "# UniPilot Agent Promotion Readiness Report" in md


def test_candidate_table_included() -> None:
    md = render_readiness_markdown_report(_sample_scorecard())
    assert "test.candidate" in md
    assert "Candidate Readiness" in md


def test_blocking_reasons_included() -> None:
    scorecard = _sample_scorecard()
    scorecard["candidates"][0]["blockingReasons"] = ["min_pass_rate_not_met"]
    md = render_readiness_markdown_report(scorecard)
    assert "min_pass_rate_not_met" in md


def test_recommendations_included() -> None:
    md = render_readiness_markdown_report(_sample_scorecard())
    assert "eligible_for_limited_promotion_review" in md


def test_report_omits_raw_text_context_blocks() -> None:
    md = render_readiness_markdown_report(_sample_scorecard())
    assert "raw_context" not in md
    assert "raw_blocks" not in md


def test_json_report_omits_forbidden_keys() -> None:
    text = str(_sample_scorecard())
    assert "chain_of_thought" not in text
    assert "raw_prompt" not in text
