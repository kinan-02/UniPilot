"""Thin async LLM adapter used by `ReasoningBlock`.

This intentionally does NOT set up its own OpenAI/base-URL/model client. It
reuses the existing shared chat LLM helpers in `app.agent.llm_client` so
there is exactly one place that knows how to build a chat model from
settings/environment.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from app.agent_core.reasoning.llm_client import agent_llm_available, build_chat_llm
from app.agent_core.reasoning.llm_json import parse_llm_json_detailed
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMAdapterError(RuntimeError):
    """Raised when the underlying LLM cannot produce a usable JSON response.

    Callers (namely `ReasoningBlock`) are expected to catch this and fail
    safely rather than letting it propagate and crash the agent.

    `str(...)` is deliberately the bare failure CODE and nothing else --
    callers dispatch on it (`str(exc) in _PARSE_FAILURE_CODES`), so folding
    the cause into the message would silently break that matching. The
    triggering exception rides on `cause` instead, rendered by `detail` for
    logs and live-eval traces.

    `detail` exists because the code alone is not diagnosable. A live-eval run
    (2026-07-16) showed seven `llm_call_failed`s the logs could not explain:
    every one was really `RuntimeError: Event loop is closed` from a cached
    client reused across pytest's per-test event loops, but the code swallowed
    that and the investigation had to reproduce it by hand to find out.
    """

    def __init__(self, code: str, *, cause: BaseException | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.cause = cause

    @property
    def detail(self) -> str:
        """The code plus the `__cause__` chain beneath it, outermost first."""
        parts = [self.code]
        seen: set[int] = set()
        exc: BaseException | None = self.cause
        while exc is not None and id(exc) not in seen:
            seen.add(id(exc))
            parts.append(f"{type(exc).__module__}.{type(exc).__name__}: {exc}")
            exc = exc.__cause__
        return " <- ".join(parts)


@runtime_checkable
class LLMAdapter(Protocol):
    """Protocol implemented by anything `ReasoningBlock` can call for completions.

    Kept minimal and async-only so fakes are trivial to write in tests.
    """

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
        ...

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
        ...


def _response_text_content(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(
                    str(getattr(block, "text", None) or getattr(block, "content", None) or block)
                )
        return "".join(parts)
    return str(content or "")


class ChatLLMAdapter:
    """Default `LLMAdapter` backed by the shared agent chat LLM client.

    Non-streaming JSON-only completions. When
    `AGENT_REASONING_STRUCTURED_OUTPUT_ENABLED` is on and a `response_schema`
    is supplied, the schema is pushed into the underlying model call via
    LangChain's `with_structured_output` (provider-native structured output)
    instead of relying purely on a free-text JSON parse — reducing how often
    `schema_repair`'s LLM-based repair loop needs to run. Off by default;
    falls back to the original free-text parse path on any structured-output
    error, or when the flag is off, so behavior is unchanged unless a caller
    explicitly opts in.
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings

    def is_available(self) -> bool:
        return agent_llm_available(settings=self._settings or get_settings())

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
        cfg = self._settings or get_settings()
        llm = build_chat_llm(
            settings=cfg,
            temperature=temperature if temperature is not None else 0.0,
            model=model,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            max_retries=max_retries,
        )
        if llm is None:
            raise LLMAdapterError("llm_unavailable")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            logger.warning("reasoning_llm_adapter_import_failed")
            raise LLMAdapterError("llm_client_import_failed") from exc

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        if response_schema is not None and cfg.is_agent_reasoning_structured_output_enabled() and streaming_queue is None:
            structured_payload = await self._complete_with_structured_output(
                llm,
                messages=messages,
                response_schema=response_schema,
                raw_model_text_out=raw_model_text_out,
            )
            if structured_payload is not None:
                return structured_payload
            # Any structured-output failure (unsupported by the provider,
            # schema rejected, parse failure) falls through to the same
            # free-text path used when the flag is off.

        try:
            if streaming_queue:
                response_text_chunks = []
                async for chunk in llm.astream(messages):
                    chunk_text = _response_text_content(chunk)
                    response_text_chunks.append(chunk_text)
                    await streaming_queue.put(chunk_text)
                full_text = "".join(response_text_chunks)
                # Mock a response object for parsing
                class _MockResponse:
                    content = full_text
                response = _MockResponse()
            else:
                response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.exception("reasoning_llm_adapter_call_failed")
            raise LLMAdapterError("llm_call_failed", cause=exc) from exc

        outcome = parse_llm_json_detailed(_response_text_content(response))
        if raw_model_text_out is not None:
            raw_model_text_out.append(_response_text_content(response))
        if outcome.payload is None:
            raise LLMAdapterError(outcome.failure_code or "invalid_json_response")
        return outcome.payload

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
        """Freeform completion with no JSON-parse gate.

        Unlike `complete_json`, a call here cannot fail with a
        `json_parse_failed`-style error -- there is no `parse_llm_json_detailed`
        step at all, so whatever the model returns is returned as-is. For a
        first-stage "generate the actual content" call in a two-stage
        generate-then-structure flow, where a later `complete_json` call
        structures this raw text into a schema.
        """
        cfg = self._settings or get_settings()
        llm = build_chat_llm(
            settings=cfg,
            temperature=temperature if temperature is not None else 0.0,
            model=model,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            max_retries=max_retries,
        )
        if llm is None:
            raise LLMAdapterError("llm_unavailable")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            logger.warning("reasoning_llm_adapter_import_failed")
            raise LLMAdapterError("llm_client_import_failed") from exc

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.exception("reasoning_llm_adapter_call_failed")
            raise LLMAdapterError("llm_call_failed", cause=exc) from exc

        return _response_text_content(response)

    async def _complete_with_structured_output(
        self,
        llm: Any,
        *,
        messages: list[Any],
        response_schema: dict[str, Any],
        raw_model_text_out: list[str] | None,
    ) -> dict[str, Any] | None:
        """Try the provider-native structured-output path; `None` means "fall back".

        Never raises — a bug or an unsupported provider here must degrade to
        the existing free-text parse path, not break the call.
        """
        try:
            structured_llm = llm.with_structured_output(response_schema, include_raw=True)
            result = await structured_llm.ainvoke(messages)
        except Exception:
            logger.warning("reasoning_structured_output_failed_falling_back")
            return None

        parsed = result.get("parsed") if isinstance(result, dict) else None
        raw_message = result.get("raw") if isinstance(result, dict) else None
        if raw_model_text_out is not None and raw_message is not None:
            raw_model_text_out.append(_response_text_content(raw_message))
        return parsed if isinstance(parsed, dict) else None
