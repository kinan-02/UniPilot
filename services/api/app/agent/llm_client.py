"""Shared chat LLM client for agent language layers (spec §31)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def agent_llm_available(*, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool((cfg.openai_api_key or "").strip())


def build_chat_llm(*, settings: Settings | None = None, temperature: float = 0.0) -> Any | None:
    """Return a LangChain ChatOpenAI instance, or None when not configured."""
    cfg = settings or get_settings()
    api_key = (cfg.openai_api_key or "").strip()
    if not api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("agent_chat_llm_unavailable_import")
        return None

    model = (cfg.openai_chat_model or "gpt-4o-mini").strip()
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
    }
    base_url = (cfg.openai_base_url or "").strip()
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return ChatOpenAI(**kwargs)
