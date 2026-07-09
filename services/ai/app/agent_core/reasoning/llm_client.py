"""Shared chat LLM client for agent language layers (spec §31)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def agent_llm_available(*, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool((cfg.openai_api_key or "").strip())


@lru_cache(maxsize=32)
def _cached_chat_llm(
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    thinking_enabled: bool,
    reasoning_effort: str | None,
) -> Any:
    """Construct (and cache) one `ChatOpenAI` per distinct settings tuple.

    Keyed on resolved primitive values rather than the `Settings` object — `Settings`
    is a mutable pydantic model, not hashable, and callers routinely construct
    independent `Settings` instances carrying identical values that should still
    share a client. `ChatOpenAI` wraps `openai.AsyncOpenAI`/`httpx.AsyncClient`,
    both safe for concurrent reuse, so sharing one instance across calls/passes
    lets connections actually get pooled instead of a fresh client (and fresh
    connections) being built on every single LLM call.
    """
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {"model": model, "temperature": temperature, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    if not thinking_enabled:
        # DeepSeek-specific (see `app/config.py::agent_llm_thinking_enabled`
        # docstring) -- merged into the raw request body via LangChain's
        # `extra_body`. A provider that doesn't recognize `thinking` is
        # expected to ignore the unknown top-level field, matching DeepSeek's
        # own documented behavior for parameters a mode doesn't support.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    elif reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    return ChatOpenAI(**kwargs)


def build_chat_llm(
    *,
    settings: Settings | None = None,
    temperature: float = 0.0,
    model: str | None = None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
) -> Any | None:
    """Return a LangChain ChatOpenAI instance, or None when not configured.

    `model`/`thinking_enabled`/`reasoning_effort` are per-call overrides for
    per-role reasoning-block tuning (AGENT_VISION.md §6.2) -- each falls back
    to the global setting when omitted, so existing callers are unaffected.
    """
    cfg = settings or get_settings()
    api_key = (cfg.openai_api_key or "").strip()
    if not api_key:
        return None

    try:
        import langchain_openai  # noqa: F401 -- import-availability check only
    except ImportError:
        logger.warning("agent_chat_llm_unavailable_import")
        return None

    resolved_model = (model or cfg.openai_chat_model or "gpt-4o-mini").strip()
    base_url = (cfg.openai_base_url or "").strip().rstrip("/")
    resolved_thinking_enabled = (
        thinking_enabled if thinking_enabled is not None else cfg.is_agent_llm_thinking_enabled()
    )
    resolved_reasoning_effort = (
        reasoning_effort if reasoning_effort is not None else cfg.resolved_agent_llm_reasoning_effort()
    )
    return _cached_chat_llm(
        api_key,
        base_url,
        resolved_model,
        round(float(temperature), 4),
        resolved_thinking_enabled,
        resolved_reasoning_effort,
    )
