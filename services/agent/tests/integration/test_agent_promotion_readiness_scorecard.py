"""Integration tests for promotion readiness scorecard (Phase 24)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.readiness_scorecard import build_readiness_scorecard
from app.agent.evaluation.replay_runner import run_eval_cases
from app.agent.evaluation.suite_loader import load_eval_suites

_CASES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases"
_SUITES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_suites"


@pytest.mark.asyncio
async def test_scorecard_uses_suite_manifests() -> None:
    cases = load_eval_cases(_CASES)
    suites = load_eval_suites(_SUITES)
    results = await run_eval_cases(cases, mode="gates_only")
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    assert len(scorecard["suiteCoverage"]) == len(suites)


@pytest.mark.asyncio
async def test_all_eval_cases_pass_before_readiness() -> None:
    cases = load_eval_cases(_CASES)
    results = await run_eval_cases(cases, mode="gates_only")
    failed = [r for r in results if r.status != "passed"]
    assert not failed, [f"{r.case_id}: {r.failures}" for r in failed]


@pytest.mark.asyncio
async def test_reports_contain_no_forbidden_keys() -> None:
    cases = load_eval_cases(_CASES)
    suites = load_eval_suites(_SUITES)
    results = await run_eval_cases(cases, mode="gates_only")
    scorecard = build_readiness_scorecard(eval_results=results, suites=suites, cases=cases)
    text = str(scorecard)
    assert "raw_context" not in text
    assert "user_message" not in text


@pytest.mark.asyncio
async def test_no_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real_llm_called")

    monkeypatch.setattr("openai.OpenAI", _fail)
    cases = load_eval_cases(_CASES)
    await run_eval_cases(cases, mode="gates_only")


@pytest.mark.asyncio
async def test_no_mongo_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mongo_write_called")

    monkeypatch.setattr("pymongo.collection.Collection.insert_one", _fail)
    cases = load_eval_cases(_CASES)
    await run_eval_cases(cases, mode="gates_only")


@pytest.mark.asyncio
async def test_no_action_proposals() -> None:
    cases = load_eval_cases(_CASES)
    results = await run_eval_cases(cases, mode="gates_only")
    for result in results:
        if result.case_id == "synthesis_promotion_blocked_by_live_actions":
            continue
        assert "proposed_actions_present" not in result.safety_failures
