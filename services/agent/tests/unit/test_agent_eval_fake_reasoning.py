"""Unit tests for fake ReasoningBlock runner (Phase 23)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.fake_reasoning import FakeReasoningBlockRunner
from app.agent.evaluation.replay_schemas import MockReasoningOutput
from app.agent.reasoning.schemas import ReasoningBlockInput


def _input(contract: str) -> ReasoningBlockInput:
    return ReasoningBlockInput(
        block_id="b1",
        agent_name="eval",
        objective="test",
        task_context={},
        output_schema_name=contract,
        output_schema={"type": "object"},
        prompt_contract_name=contract,
    )


@pytest.mark.asyncio
async def test_returns_configured_output_by_contract_name() -> None:
    runner = FakeReasoningBlockRunner(
        [MockReasoningOutput(contract_name="planner", output={"status": "ok"})]
    )
    out = await runner.run(_input("planner"))
    assert out.result == {"status": "ok"}


@pytest.mark.asyncio
async def test_respects_call_index() -> None:
    runner = FakeReasoningBlockRunner(
        [
            MockReasoningOutput(contract_name="planner", output={"n": 0}, call_index=0),
            MockReasoningOutput(contract_name="planner", output={"n": 1}, call_index=1),
        ]
    )
    first = await runner.run(_input("planner"))
    second = await runner.run(_input("planner"))
    assert first.result == {"n": 0}
    assert second.result == {"n": 1}


@pytest.mark.asyncio
async def test_deterministic_fallback_when_missing() -> None:
    runner = FakeReasoningBlockRunner([])
    out = await runner.run(_input("missing"))
    assert out.status == "failed"
    assert out.schema_valid is False


@pytest.mark.asyncio
async def test_never_calls_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real_llm_called")

    monkeypatch.setattr("openai.OpenAI", _fail)
    runner = FakeReasoningBlockRunner(
        [MockReasoningOutput(contract_name="planner", output={"status": "ok"})]
    )
    await runner.run(_input("planner"))
