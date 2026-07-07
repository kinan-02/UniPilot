"""Integration tests for offline eval replay runner (Phase 23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.replay_schemas import EvalExpectedOutcome, MockReasoningOutput
from app.agent.evaluation.replay_runner import run_eval_case, run_eval_cases

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases"


@pytest.mark.asyncio
async def test_gates_only_runs_over_fixture_directory() -> None:
    cases = load_eval_cases(_FIXTURES)
    results = await run_eval_cases(cases, mode="gates_only")
    assert len(results) == len(cases)


@pytest.mark.asyncio
async def test_initial_fixtures_produce_expected_outcomes() -> None:
    cases = load_eval_cases(_FIXTURES)
    results = await run_eval_cases(cases, mode="gates_only")
    failed = [r for r in results if r.status != "passed"]
    assert not failed, [f"{r.case_id}: {r.failures}" for r in failed]


@pytest.mark.asyncio
async def test_shadow_replay_runs_with_fake_reasoning() -> None:
    case = next(c for c in load_eval_cases(_FIXTURES) if c.id == "synthesis_promotion_valid_text_only")
    case = case.model_copy(
        update={
            "mock_reasoning_outputs": [
                MockReasoningOutput(
                    contract_name="synthesis_composer",
                    output={"status": "candidate_ready", "decision_summary": "mock"},
                )
            ]
        }
    )
    result = await run_eval_case(case, mode="shadow_replay")
    assert result.status in {"passed", "failed"}
    assert result.status != "error"


@pytest.mark.asyncio
async def test_failed_case_reports_failure() -> None:
    cases = load_eval_cases(_FIXTURES)
    case = cases[0].model_copy(
        update={"expected": EvalExpectedOutcome(expected_intent="definitely_wrong_intent")}
    )
    result = await run_eval_case(case, mode="gates_only")
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_unsafe_case_is_blocked() -> None:
    case = next(c for c in load_eval_cases(_FIXTURES) if c.id == "monitor_unsafe_output_blocks_promotion")
    result = await run_eval_case(case, mode="gates_only")
    assert result.status == "passed"
    assert result.actual_synthesis_promotion == "blocked"


@pytest.mark.asyncio
async def test_no_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real_llm_called")

    monkeypatch.setattr("openai.OpenAI", _fail)
    cases = load_eval_cases(_FIXTURES)
    await run_eval_cases(cases, mode="gates_only")


@pytest.mark.asyncio
async def test_no_mongo_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mongo_write_called")

    monkeypatch.setattr("pymongo.collection.Collection.insert_one", _fail)
    monkeypatch.setattr("pymongo.collection.Collection.update_one", _fail)
    cases = load_eval_cases(_FIXTURES)
    await run_eval_cases(cases, mode="gates_only")


@pytest.mark.asyncio
async def test_no_action_proposals() -> None:
    cases = load_eval_cases(_FIXTURES)
    results = await run_eval_cases(cases, mode="gates_only")
    for result in results:
        if result.case_id == "synthesis_promotion_blocked_by_live_actions":
            continue
        assert "proposed_actions_present" not in result.safety_failures
