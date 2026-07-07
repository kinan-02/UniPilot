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
def _cached_chat_llm(api_key: str, base_url: str, model: str, temperature: float) -> Any:
    """Construct (and cache) one `ChatOpenAI` per distinct `(api_key, base_url, model,
    temperature)` tuple.

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
    return ChatOpenAI(**kwargs)


def build_chat_llm(*, settings: Settings | None = None, temperature: float = 0.0) -> Any | None:
    """Return a LangChain ChatOpenAI instance, or None when not configured."""
    cfg = settings or get_settings()
    api_key = (cfg.openai_api_key or "").strip()
    if not api_key:
        return None

    try:
        import langchain_openai  # noqa: F401 -- import-availability check only
    except ImportError:
        logger.warning("agent_chat_llm_unavailable_import")
        return None

    model = (cfg.openai_chat_model or "gpt-4o-mini").strip()
    base_url = (cfg.openai_base_url or "").strip().rstrip("/")
    return _cached_chat_llm(api_key, base_url, model, round(float(temperature), 4))
