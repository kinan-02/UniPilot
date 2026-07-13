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

import asyncio
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
    parsed_response: dict[str, Any] | None
    timeout: float | None
    max_retries: int | None
    # "json" for a `complete_json` call, "text" for a `complete_text` call --
    # kept in one ordered list (rather than two separate lists) so a
    # two-stage flow's stage1/stage2 calls stay in their real call order in
    # the written log.
    kind: str = "json"
    # A call that raised (e.g. hit its own `timeout`) used to leave NO
    # record at all -- found the hard way while investigating a case that
    # "passed" in 75s with only 2 recorded calls: the Planner's first call
    # had actually timed out and BaseReasoningBlock.run()'s catch-all
    # swallowed it into a generic fallback, but the log looked like the
    # Planner was simply never invoked. Recording the exception here closes
    # that blind spot for future live-eval investigations.
    error: str | None = None


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
        streaming_queue: asyncio.Queue[str] | None = None,
    ) -> dict[str, Any]:
        local_raw: list[str] = []
        try:
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
                streaming_queue=streaming_queue,
            )
        except Exception as exc:
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
                    parsed_response=None,
                    timeout=timeout,
                    max_retries=max_retries,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
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
        try:
            result = await self._adapter.complete_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                model=model,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                max_retries=max_retries,
            )
        except Exception as exc:
            self.calls.append(
                _RecordedCall(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    model=model,
                    thinking_enabled=thinking_enabled,
                    reasoning_effort=reasoning_effort,
                    response_schema=None,
                    raw_response_text="",
                    parsed_response=None,
                    timeout=timeout,
                    max_retries=max_retries,
                    kind="text",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
        self.calls.append(
            _RecordedCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                model=model,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                response_schema=None,
                raw_response_text=result,
                parsed_response=None,
                timeout=timeout,
                max_retries=max_retries,
                kind="text",
            )
        )
        return result


def _to_jsonable(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


class LiveEvalLog:
    """Accumulates one entry per test case across a whole test-file run,
    written to one timestamped JSON file (path fixed at construction, not
    recomputed per write) that is now rewritten after EVERY `record_case`
    call, not just once at teardown. A run that times out case-by-case can
    take 25+ minutes; needing the whole run to finish before a single
    case's own call trace could be inspected made every mid-run
    investigation this session slower than it needed to be -- an
    in-progress run's log is now readable the moment each case finishes,
    and a run killed partway through (or one that crashes) still leaves
    every case recorded so far on disk instead of nothing."""

    def __init__(self, suite_name: str) -> None:
        self._suite_name = suite_name
        self._cases: list[dict[str, Any]] = []
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._path = _LOG_DIR / f"{suite_name}-{timestamp}.json"

    def record_case(self, case_name: str, adapter: LoggingLLMAdapter, **extra: Any) -> None:
        self._cases.append(
            {
                "case": case_name,
                "calls": [
                    {
                        "kind": call.kind,
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
                        "error": call.error,
                    }
                    for call in adapter.calls
                ],
                **{key: _to_jsonable(value) for key, value in extra.items()},
            }
        )
        self.write()

    def write(self) -> Path:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        # `default=str` is a defensive fallback, not the primary path: a
        # live-eval file passing a raw (non-`mode="json"`) `.model_dump()`
        # can still leak a `datetime`/`ObjectId` into `self._cases`. Without
        # this, that one bad value crashes the whole `write()` call --
        # discarding every case's log from a real, expensive (LLM + Mongo)
        # run, found the hard way when a 47-minute run's entire log was lost
        # to exactly this.
        self._path.write_text(json.dumps(self._cases, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return self._path
