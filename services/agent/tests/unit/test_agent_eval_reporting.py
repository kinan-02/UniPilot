"""Unit tests for offline eval reporting (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.reporting import build_eval_report, render_markdown_eval_report
from app.agent.evaluation.replay_schemas import EvalCaseResult


def test_markdown_report_includes_failures() -> None:
    results = [
        EvalCaseResult(
            case_id="c1",
            name="Case 1",
            status="failed",
            failures=["expected_intent_mismatch"],
            gates=[],
        )
    ]
    report = build_eval_report(results)
    md = render_markdown_eval_report(report)
    assert "expected_intent_mismatch" in md
    assert "c1" in md


def test_json_report_omits_forbidden_keys() -> None:
    results = [EvalCaseResult(case_id="c1", name="Case 1", status="passed")]
    report = build_eval_report(results)
    text = str(report)
    assert "raw_context" not in text
    assert "chain_of_thought" not in text


def test_markdown_report_omits_raw_text_context_blocks() -> None:
    results = [
        EvalCaseResult(
            case_id="c1",
            name="Case 1",
            status="failed",
            failures=["forbidden_claim_present"],
        )
    ]
    report = build_eval_report(results)
    md = render_markdown_eval_report(report)
    assert "raw_context" not in md
    assert "raw_blocks" not in md
