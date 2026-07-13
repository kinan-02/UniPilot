"""Shared fixtures for agent_core tests.

`FakeLLMAdapter` mirrors the exact pattern already used by
`services/agent`'s own `tests/agent/reasoning/test_reasoning_block.py` --
a deterministic fake `LLMAdapter` returning queued JSON responses in order,
so no real LLM call is ever made.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


class FakeLLMAdapter:
    def __init__(self, responses: list[dict[str, Any]], text_responses: list[str] | None = None) -> None:
        self._responses = list(responses)
        self._text_responses = list(text_responses or [])
        self.calls: list[dict[str, Any]] = []
        self.text_calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "model": model,
                "thinking_enabled": thinking_enabled,
                "reasoning_effort": reasoning_effort,
                "response_schema": response_schema,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        if not self._responses:
            raise AssertionError("FakeLLMAdapter exhausted its queued responses")
        response = self._responses.pop(0)
        if raw_model_text_out is not None:
            raw_model_text_out.append(json.dumps(response))
        return response

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        model: str | None = None,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        self.text_calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "model": model,
                "thinking_enabled": thinking_enabled,
                "reasoning_effort": reasoning_effort,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        if not self._text_responses:
            raise AssertionError("FakeLLMAdapter exhausted its queued text_responses")
        return self._text_responses.pop(0)


@pytest.fixture
def fake_llm_adapter_factory():
    def _build(responses: list[dict[str, Any]], text_responses: list[str] | None = None) -> FakeLLMAdapter:
        return FakeLLMAdapter(responses, text_responses=text_responses)

    return _build
