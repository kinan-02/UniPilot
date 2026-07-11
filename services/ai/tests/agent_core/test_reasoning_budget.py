"""Unit tests for `BudgetedLLMAdapter` (docs/agent/TOOL_PRIMITIVES_OPEN_GAPS.md
live-eval-readiness audit): the per-turn ceiling on real LLM calls."""

from __future__ import annotations

import pytest

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.reasoning.reasoning_budget import BudgetedLLMAdapter


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls_made = 0

    async def complete_json(self, **_kwargs) -> dict:
        self.calls_made += 1
        return {"status": "ok"}


async def test_delegates_calls_while_under_budget() -> None:
    fake = _FakeAdapter()
    adapter = BudgetedLLMAdapter(fake, max_calls=3)

    for _ in range(3):
        result = await adapter.complete_json(system_prompt="s", user_prompt="u")
        assert result == {"status": "ok"}

    assert fake.calls_made == 3
    assert adapter.calls_made == 3


async def test_raises_llm_adapter_error_once_budget_exhausted() -> None:
    fake = _FakeAdapter()
    adapter = BudgetedLLMAdapter(fake, max_calls=1)

    await adapter.complete_json(system_prompt="s", user_prompt="u")
    with pytest.raises(LLMAdapterError):
        await adapter.complete_json(system_prompt="s", user_prompt="u")

    # The refused call must never reach the wrapped adapter -- no real LLM
    # call (no real cost) is made once the budget is exhausted.
    assert fake.calls_made == 1


async def test_zero_budget_refuses_the_very_first_call() -> None:
    fake = _FakeAdapter()
    adapter = BudgetedLLMAdapter(fake, max_calls=0)

    with pytest.raises(LLMAdapterError):
        await adapter.complete_json(system_prompt="s", user_prompt="u")

    assert fake.calls_made == 0
