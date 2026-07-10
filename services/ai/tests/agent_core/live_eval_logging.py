"""Shared logging harness for live-eval test files.

Wraps a real `ChatLLMAdapter` to record every `complete_json` call (both
prompts, call parameters, and the raw + parsed response) so the actual
evidence behind a live-eval run survives past one test session's terminal
output -- not just a paraphrase of it. Test-only; never used from any
production code path.

Each live-eval test file gets its own `LiveEvalLog` (one JSON file per run,
one entry per case, each entry holding every LLM call made for that case in
order) written to `tests/agent_core/live_eval_logs/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter

_LOG_DIR = Path(__file__).resolve().parent / "live_eval_logs"


@dataclass
class _RecordedCall:
    system_prompt: str
    user_prompt: str
    temperature: float | None
    model: str | None
    thinking_enabled: bool | None
    reasoning_effort: str | None
    response_schema: dict[str, Any] | None
    raw_response_text: str
    parsed_response: dict[str, Any]
    timeout: float | None
    max_retries: int | None


class LoggingLLMAdapter:
    """Wraps a real `LLMAdapter`, recording every call it makes."""

    def __init__(self, adapter: ChatLLMAdapter | None = None) -> None:
        self._adapter = adapter or ChatLLMAdapter()
        self.calls: list[_RecordedCall] = []

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
    ) -> dict[str, Any]:
        local_raw: list[str] = []
        result = await self._adapter.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            model=model,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            response_schema=response_schema,
            raw_model_text_out=local_raw,
            timeout=timeout,
            max_retries=max_retries,
        )
        if raw_model_text_out is not None and local_raw:
            raw_model_text_out.append(local_raw[0])
        self.calls.append(
            _RecordedCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                model=model,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                response_schema=response_schema,
                raw_response_text=local_raw[0] if local_raw else "",
                parsed_response=result,
                timeout=timeout,
                max_retries=max_retries,
            )
        )
        return result


def _to_jsonable(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


class LiveEvalLog:
    """Accumulates one entry per test case across a whole test-file run,
    written to one timestamped JSON file when `write()` is called (a
    module-scoped fixture calls this once, on teardown, after every case in
    the file has run)."""

    def __init__(self, suite_name: str) -> None:
        self._suite_name = suite_name
        self._cases: list[dict[str, Any]] = []

    def record_case(self, case_name: str, adapter: LoggingLLMAdapter, **extra: Any) -> None:
        self._cases.append(
            {
                "case": case_name,
                "calls": [
                    {
                        "system_prompt": call.system_prompt,
                        "user_prompt": call.user_prompt,
                        "params": {
                            "temperature": call.temperature,
                            "model": call.model,
                            "thinking_enabled": call.thinking_enabled,
                            "reasoning_effort": call.reasoning_effort,
                            "timeout": call.timeout,
                            "max_retries": call.max_retries,
                        },
                        "raw_response_text": call.raw_response_text,
                        "parsed_response": call.parsed_response,
                    }
                    for call in adapter.calls
                ],
                **{key: _to_jsonable(value) for key, value in extra.items()},
            }
        )

    def write(self) -> Path:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = _LOG_DIR / f"{self._suite_name}-{timestamp}.json"
        path.write_text(json.dumps(self._cases, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
