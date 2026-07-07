"""Unit tests for final-answer eval performance features (Phase 28.1)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent.evaluation.agent_setup import eval_password_hash
from app.agent.evaluation.deterministic_fast_runner import (
    deterministic_fast_supported,
    run_deterministic_fast_eval_case,
)
from app.agent.evaluation.eval_llm_tracker import EvalLlmCallTracker
from app.agent.evaluation.eval_thresholds import (
    EvalThresholdsFile,
    SuiteThresholds,
    evaluate_thresholds,
    load_eval_thresholds,
    resolve_suite_thresholds,
)
from app.agent.evaluation.eval_timing import CaseTiming, aggregate_timing_summary
from app.agent.evaluation.final_answer_eval import (
    FactCheckResult,
    GoldenAnswerCase,
    build_final_answer_eval_report,
)
from app.agent.evaluation.wiki_eval_cache import (
    cache_stats,
    cached_course_by_code,
    reset_wiki_eval_cache,
    warm_wiki_eval_cache,
)


def _regulation_case() -> GoldenAnswerCase:
    return GoldenAnswerCase(
        id="perf_case",
        query_type="regulation_reasoning",
        difficulty="easy",
        language="en",
        user_request=(
            "I took Moed A in a course and got 72. Then I decided to try Moed B to improve my grade, "
            "but I only got 58. What is my official final grade for this course?"
        ),
        correct_summary="Final grade is 58.",
        key_facts=["The final grade is 58, not 72"],
        source_wiki_pages=["wiki/concepts/regulations-undergraduate.md"],
    )


def test_timing_fields_exist_in_report() -> None:
    timing = CaseTiming(case_id="perf_case", total_ms=120.0, llm_call_count=2, agent_mode="full_live")
    report = build_final_answer_eval_report(
        [],
        timings=[timing],
        timing_summary=aggregate_timing_summary([timing], total_run_ms=120.0),
        agent_mode="full_live",
    )
    assert report["timingSummary"]["totalRunMs"] == 120.0
    assert report["agentMode"] == "full_live"


def test_timing_summary_aggregation() -> None:
    timings = [
        CaseTiming(case_id="a", total_ms=100.0, llm_call_count=1),
        CaseTiming(case_id="b", total_ms=300.0, llm_call_count=2),
    ]
    summary = aggregate_timing_summary(timings, total_run_ms=450.0)
    assert summary["averageCaseMs"] == 200.0
    assert summary["totalLlmCalls"] == 3
    assert summary["slowestCases"][0]["caseId"] == "b"


def test_llm_call_counting_tracker() -> None:
    tracker = EvalLlmCallTracker(case_id="case")
    tracker.on_llm_call(
        case_id="case",
        phase="agent_turn",
        contract_name="task_understanding_v1",
        contract_version="1",
        prompt_text="prompt",
        raw_model_output="{}",
        parsed_json_preview={},
        schema_valid=True,
        status="completed",
        repair_attempted=False,
        repair_succeeded=False,
        fallback_used=False,
        warnings=[],
        duration_ms=150.0,
    )
    count, total_ms = tracker.snapshot()
    assert count == 1
    assert total_ms == 150.0


def test_deterministic_fast_supported_for_regulation_case() -> None:
    assert deterministic_fast_supported(_regulation_case().user_request)


@pytest.mark.asyncio
async def test_deterministic_fast_skips_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fact = FactCheckResult(fact="The final grade is 58, not 72", status="present")

    async def _fake_judge(**kwargs):  # noqa: ANN003
        return [fact], []

    monkeypatch.setattr(
        "app.agent.evaluation.final_answer_judge.evaluate_facts_with_judge",
        _fake_judge,
    )
    monkeypatch.setattr(
        "app.agent.evaluation.deterministic_fast_runner.try_compose_deterministic_answer",
        lambda *_args, **_kwargs: ("Your official final grade is 58.", ["wiki/concepts/regulations-undergraduate.md"]),
    )
    result, _trace, timing = await run_deterministic_fast_eval_case(None, _regulation_case())
    assert timing.llm_call_count == 0
    assert timing.agent_mode == "deterministic_fast"
    assert result.final_answer


@pytest.mark.asyncio
async def test_deterministic_fast_unsupported_case() -> None:
    case = GoldenAnswerCase(
        id="unsupported",
        query_type="unknown",
        difficulty="hard",
        language="en",
        user_request="Tell me a joke about exams.",
        correct_summary="n/a",
        key_facts=["not applicable"],
    )
    result, _trace, timing = await run_deterministic_fast_eval_case(None, case)
    assert "deterministic_fast_unsupported" in result.failures
    assert timing.llm_call_count == 0


def test_threshold_evaluation_passes_and_fails() -> None:
    report = {
        "summary": {
            "total_cases": 2,
            "passed_cases": 1,
            "average_fact_coverage": 0.85,
            "total_facts_contradicted": 0,
        },
        "caseResults": [{"sourceWarnings": []}, {"sourceWarnings": ["x"]}],
    }
    passed = evaluate_thresholds(
        report,
        thresholds=SuiteThresholds(min_pass_rate=0.5, min_average_fact_coverage=0.8, max_contradictions=0),
    )
    assert passed["passed"] is True

    failed = evaluate_thresholds(
        report,
        thresholds=SuiteThresholds(min_pass_rate=1.0),
    )
    assert failed["passed"] is False
    assert "min_pass_rate" in failed["violations"]


def test_load_eval_thresholds_file(tmp_path: Path) -> None:
    payload = {"golden": {"minPassRate": 1.0}}
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_eval_thresholds(path)
    assert isinstance(loaded, EvalThresholdsFile)
    assert loaded.golden is not None
    assert loaded.golden.min_pass_rate == 1.0


def test_resolve_suite_thresholds_broader() -> None:
    thresholds = EvalThresholdsFile(broader=SuiteThresholds(min_pass_rate=0.8))
    resolved = resolve_suite_thresholds(thresholds, cases_path="eval_sets/eval_cases_broader_academic.json")
    assert resolved.min_pass_rate == 0.8


def test_wiki_cache_prevents_repeated_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reset_wiki_eval_cache()
    wiki_root = tmp_path / "wiki"
    courses_dir = wiki_root / "courses" / "023-cs"
    courses_dir.mkdir(parents=True)
    page = courses_dir / "02360343-theory-of-computation.md"
    page.write_text(
        "---\ncourse_code: '02360343'\ntitle: Theory\ncredits: '3.0'\nlevel: undergraduate\n---\n\n"
        "**Prerequisites:** none\n**Required in:** [[track-computer-science-general-4year]]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CATALOG_VAULT_WIKI_PATH", str(wiki_root))
    warm_wiki_eval_cache()
    cached_course_by_code(wiki_root, "02360343")
    stats_after_first = cache_stats()
    page.write_text("corrupted", encoding="utf-8")
    second = cached_course_by_code(wiki_root, "02360343")
    stats_after_second = cache_stats()
    assert second is not None
    assert stats_after_second["courseLookupHits"] >= stats_after_first["courseLookupHits"]


def test_eval_password_hash_is_cached() -> None:
    first = eval_password_hash()
    second = eval_password_hash()
    assert first == second


def test_trace_on_failure_write_policy() -> None:
    def should_write(status: str, *, trace_on_failure: bool) -> bool:
        if not trace_on_failure:
            return True
        return status in {"failed", "partial", "errored"}

    assert should_write("passed", trace_on_failure=True) is False
    assert should_write("failed", trace_on_failure=True) is True
    assert should_write("passed", trace_on_failure=False) is True


def test_concurrency_preserves_output_order() -> None:
    async def run_cases() -> list[str]:
        async def fake_case(index: int) -> tuple[int, str]:
            await asyncio.sleep(0.01 * (2 - index))
            return index, f"case_{index}"

        outcomes = await asyncio.gather(fake_case(0), fake_case(1), fake_case(2))
        ordered: list[str | None] = [None, None, None]
        for index, label in sorted(outcomes, key=lambda item: item[0]):
            ordered[index] = label
        return [item for item in ordered if item is not None]

    assert asyncio.run(run_cases()) == ["case_0", "case_1", "case_2"]


def test_main_report_includes_llm_call_count_per_case() -> None:
    timing = CaseTiming(case_id="c1", llm_call_count=0, agent_mode="deterministic_fast")
    from app.agent.evaluation.final_answer_eval import FinalAnswerCaseResult

    result = FinalAnswerCaseResult(
        case_id="c1",
        status="passed",
        query_type="x",
        difficulty="easy",
        user_request="q",
        final_answer="a",
    )
    report = build_final_answer_eval_report([result], timings=[timing], agent_mode="deterministic_fast")
    case = report["caseResults"][0]
    assert case["llmCallCount"] == 0
    assert case["timing"]["llmCallCount"] == 0
