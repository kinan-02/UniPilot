"""Unit tests for golden-set final answer evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.evaluation.final_answer_eval import (
    FinalAnswerCaseResult,
    GoldenAnswerCase,
    aggregate_final_answer_summary,
    build_final_answer_eval_report,
    evaluate_fact_deterministic,
    load_golden_answer_cases,
    normalize_credit_value,
    normalize_eval_text,
    render_final_answer_markdown_report,
    score_final_answer_case,
)

_EVAL_SET = Path(__file__).resolve().parents[2] / "eval_sets" / "eval_cases.json"


def _case(case_id: str) -> GoldenAnswerCase:
    return next(case for case in load_golden_answer_cases(_EVAL_SET) if case.id == case_id)


def test_load_golden_answer_cases_validates_metadata_count(tmp_path: Path) -> None:
    payload = json.loads(_EVAL_SET.read_text(encoding="utf-8"))
    payload["metadata"]["case_count"] = 999
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="case_count"):
        load_golden_answer_cases(bad_path)


def test_load_golden_answer_cases_rejects_empty_key_facts(tmp_path: Path) -> None:
    payload = json.loads(_EVAL_SET.read_text(encoding="utf-8"))
    payload["cases"][0]["correct_answer"]["key_facts"] = []
    bad_path = tmp_path / "empty_facts.json"
    bad_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="key_facts"):
        load_golden_answer_cases(bad_path)


def test_load_golden_answer_cases_success() -> None:
    cases = load_golden_answer_cases(_EVAL_SET)
    assert len(cases) == 25
    assert cases[0].id == "case_001"
    assert cases[0].key_facts


def test_normalize_eval_text_collapses_whitespace_and_dashes() -> None:
    text = normalize_eval_text("Final  grade\u2014is  58")
    assert text == "Final grade-is 58"


def test_normalize_credit_value_strips_trailing_zero() -> None:
    assert normalize_credit_value("155.0") == "155"


def test_final_grade_58_present() -> None:
    fact = "The final grade is 58, not 72"
    answer = "Your official final grade is 58 because Moed B is the determining grade."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "present"


def test_final_grade_72_contradicted_when_fact_says_58() -> None:
    fact = "The final grade is 58, not 72"
    answer = "Your final grade is 72 because that was your Moed A score."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "contradicted"


def test_total_credits_155_present_with_decimal_normalization() -> None:
    fact = "Total credits required: 155.0"
    answer = "You need 155 credits total for the 4-year General CS track."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "present"


def test_total_credits_118_contradicted_when_fact_says_155() -> None:
    fact = "Total credits required: 155.0"
    answer = "The 3-year track requires 118.5 credits total."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "contradicted"


def test_track_slug_present_exactly() -> None:
    fact = "Required in track: track-software-engineering"
    answer = "This course is required in track-software-engineering and track-cs-physics."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "present"


def test_missing_prerequisite_marked_missing() -> None:
    fact = "Prerequisite 2: 02340247 — אלגוריתמים 1 (Algorithms 1)"
    answer = "Prerequisite 1 is 02340129. No other prerequisites are listed."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "missing"


def test_or_condition_logic_present() -> None:
    fact = "Any single condition is sufficient — all 8 are OR-conditions"
    answer = "A student enters non-regular standing if any one of the eight conditions is met."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status in {"present", "partial"}


def test_and_condition_wording_contradicts_or_requirement() -> None:
    fact = "Any single condition is sufficient — all 8 are OR-conditions"
    answer = "The student must meet all conditions before being placed in non-regular standing."
    result = evaluate_fact_deterministic(fact, answer)
    assert result.status == "contradicted"


def test_score_final_answer_case_passes_high_coverage() -> None:
    case = _case("case_002")
    answer = (
        "The determining grade is always the last grade taken. Your final grade is 58, not 72. "
        "58 is a passing grade because the passing threshold is 55. "
        "Both Moed A and Moed B grades count in cumulative GPA calculations."
    )
    fact_results = [evaluate_fact_deterministic(fact, answer) for fact in case.key_facts]
    result = score_final_answer_case(case, final_answer=answer, fact_results=fact_results)
    assert result.status in {"passed", "partial"}
    assert result.fact_coverage >= 0.65


def test_aggregate_final_answer_summary() -> None:
    results = [
        FinalAnswerCaseResult(
            case_id="a",
            status="passed",
            query_type="x",
            difficulty="easy",
            user_request="q",
            final_answer="a",
            required_fact_count=4,
            facts_present=4,
            fact_coverage=1.0,
        ),
        FinalAnswerCaseResult(
            case_id="b",
            status="failed",
            query_type="x",
            difficulty="easy",
            user_request="q",
            final_answer="a",
            required_fact_count=4,
            facts_present=1,
            facts_missing=3,
            fact_coverage=0.25,
        ),
    ]
    summary = aggregate_final_answer_summary(results)
    assert summary.total_cases == 2
    assert summary.passed_cases == 1
    assert summary.failed_cases == 1
    assert summary.total_required_facts == 8


def test_build_and_render_final_answer_report() -> None:
    result = FinalAnswerCaseResult(
        case_id="case_001",
        status="partial",
        query_type="course_prerequisites_lookup",
        difficulty="easy",
        user_request="What are prerequisites?",
        final_answer="Course 02360343 requires 02340129.",
        fact_results=[
            evaluate_fact_deterministic("Course code: 02360343", "Course 02360343 requires 02340129."),
            evaluate_fact_deterministic(
                "Prerequisite 2: 02340247 — אלגוריתמים 1 (Algorithms 1)",
                "Course 02360343 requires 02340129.",
            ),
        ],
        required_fact_count=2,
        facts_present=1,
        facts_missing=1,
        fact_coverage=0.5,
    )
    report = build_final_answer_eval_report([result])
    markdown = render_final_answer_markdown_report(report)
    assert report["summary"]["total_cases"] == 1
    assert report["caseResults"][0]["caseId"] == "case_001"
    assert "# UniPilot Final Answer Evaluation" in markdown
    assert "case_001" in markdown


def test_evaluate_final_answer_only_logic_without_runner_import() -> None:
    case = _case("case_002")
    answer = (
        "The determining grade is always the last grade taken. Your final grade is 58, not 72. "
        "58 is a passing grade because the passing threshold is 55."
    )
    fact_results = [evaluate_fact_deterministic(fact, answer) for fact in case.key_facts]
    result = score_final_answer_case(case, final_answer=answer, fact_results=fact_results)
    assert result.facts_contradicted == 0
    assert result.fact_coverage >= 0.5
