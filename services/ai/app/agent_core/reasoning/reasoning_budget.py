"""Per-turn ceiling on real LLM calls.

`agent_core` has no equivalent to the legacy `services/agent` stack's own
`AGENT_EVAL_FULL_LLM_MAX_TOTAL_REASONING_CALLS` -- nothing bounds the total
number of real, billed LLM calls a single turn can make. Existing loops
(`DEFAULT_MAX_PLANNER_INVOCATIONS`, `DEFAULT_MAX_TASK_HANDLER_ROUNDS`,
each role's own `default_max_iterations`) bound *rounds*/*iterations* at
their own level, but nothing stops a wide plan (many steps, several of them
non-atomic, each with its own nested rounds) from compounding into a very
large number of real calls for one user question.

`BudgetedLLMAdapter` wraps any `LLMAdapter` and counts calls across however
many reasoning blocks share one instance (one instance per turn -- construct
it where the turn's own `llm_adapter` is built, e.g. `routes/advise.py`).
Once exhausted, it raises `LLMAdapterError` -- the SAME exception
`ReasoningBlock.run()` already catches and turns into a graceful
`status="failed"` output with `warnings=["llm_adapter_error: ...",
"fallback_used"]` (see `reasoning_block.py`'s own "Never raises for LLM
unavailability/failure" docstring). Every call site in the system --
Planner, classifier, step_prep, specialists, success-check, Monitor --
already goes through that one shared path, so this needs no other code to
change: a budget-exhausted turn degrades exactly like an LLM outage would,
which every existing replan/exhaustion loop already handles safely.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter, LLMAdapterError

DEFAULT_MAX_REASONING_CALLS_PER_TURN = 80


class BudgetedLLMAdapter:
    """Wraps `adapter`, refusing calls once `max_calls` real calls have
    already been made through this instance."""

    def __init__(self, adapter: LLMAdapter, *, max_calls: int = DEFAULT_MAX_REASONING_CALLS_PER_TURN) -> None:
        self._adapter = adapter
        self._max_calls = max_calls
        self.calls_made = 0

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        model: str | None = None,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
        response_schema: dict[str, Any] | None = None,
        raw_model_text_out: list[str] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        streaming_queue: asyncio.Queue[str] | None = None,
    ) -> dict[str, Any]:
        if self.calls_made >= self._max_calls:
            raise LLMAdapterError(
                f"reasoning_call_budget_exhausted: {self._max_calls} calls already made this turn"
            )
        self.calls_made += 1
        return await self._adapter.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            model=model,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            response_schema=response_schema,
            raw_model_text_out=raw_model_text_out,
            timeout=timeout,
            max_retries=max_retries,
            streaming_queue=streaming_queue,
        )


__all__ = ["DEFAULT_MAX_REASONING_CALLS_PER_TURN", "BudgetedLLMAdapter"]
