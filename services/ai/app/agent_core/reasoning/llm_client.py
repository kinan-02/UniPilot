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


def _apply_reasoning_kwargs(
    kwargs: dict[str, Any],
    *,
    provider: str,
    thinking_enabled: bool,
    reasoning_effort: str | None,
) -> None:
    """Translate the ABSTRACT thinking_enabled/reasoning_effort intent every
    reasoning-block caller (Request Understanding, the Planner, ...)
    expresses through `LLMCallParameters` into whatever wire format the
    ACTIVE provider (`Settings.agent_llm_provider`) actually expects.

    This is the ONLY place in the codebase that needs to change when a new
    provider's reasoning-control mechanism differs -- no caller ever needs
    to know, or be edited for, which provider is currently active.

    `reasoning_effort` itself needs no per-provider translation: passing it
    as a direct `reasoning_effort` kwarg is both DeepSeek's own confirmed-
    working mechanism (exercised across every live Planner call so far) and
    OpenAI's own documented parameter for the same concept. The one thing
    that IS provider-specific is how to request "no reasoning at all":
    DeepSeek needs an explicit opt-out (`extra_body={"thinking": {"type":
    "disabled"}}`, DeepSeek's own documented shape); other providers simply
    never receive a `reasoning_effort` kwarg in that case, which is already
    "no reasoning requested" for them -- sending DeepSeek's opt-out field to
    a provider that doesn't recognize it would be meaningless wire noise,
    not a graceful no-op to rely on.
    """
    if provider == "deepseek" and not thinking_enabled:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        return
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort


@lru_cache(maxsize=32)
def _cached_chat_llm(
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    provider: str,
    thinking_enabled: bool,
    reasoning_effort: str | None,
    timeout: float | None,
    max_retries: int | None,
) -> Any:
    """Construct (and cache) one `ChatOpenAI` per distinct settings tuple.

    Keyed on resolved primitive values rather than the `Settings` object — `Settings`
    is a mutable pydantic model, not hashable, and callers routinely construct
    independent `Settings` instances carrying identical values that should still
    share a client. `ChatOpenAI` wraps `openai.AsyncOpenAI`/`httpx.AsyncClient`,
    both safe for concurrent reuse, so sharing one instance across calls/passes
    lets connections actually get pooled instead of a fresh client (and fresh
    connections) being built on every single LLM call.

    `timeout`/`max_retries`/`provider` are part of the cache key deliberately
    -- if they weren't, the first caller to request a given (model,
    temperature, ...) combination would "win" the cache slot, and every
    other caller asking for the *same* combination but a *different*
    timeout/retry/provider setting would silently get that first caller's
    client instead of its own. One component (e.g. the Planner) setting its
    own timeout, or a provider swap, must never leak into or get overridden
    by another caller's client.

    `temperature` is passed through exactly as requested, unconditionally --
    deliberately NOT forced to any provider-specific fixed value here, even
    though some reasoning-capable models only accept a narrow range. If a
    provider ever rejects a given temperature, that should surface as a
    real API error to investigate, not be silently rewritten underneath the
    caller.
    """
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {"model": model, "temperature": temperature, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    if timeout is not None:
        kwargs["timeout"] = timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    _apply_reasoning_kwargs(
        kwargs, provider=provider, thinking_enabled=thinking_enabled, reasoning_effort=reasoning_effort
    )
    return ChatOpenAI(**kwargs)


def build_chat_llm(
    *,
    settings: Settings | None = None,
    temperature: float = 0.0,
    model: str | None = None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> Any | None:
    """Return a LangChain ChatOpenAI instance, or None when not configured.

    `model`/`thinking_enabled`/`reasoning_effort`/`timeout`/`max_retries` are
    per-call overrides for per-role reasoning-block tuning (AGENT_VISION.md
    §6.2) -- each falls back to the global setting (or the SDK's own
    default, for `timeout`/`max_retries`) when omitted, so existing callers
    are unaffected. Which provider's wire format to translate into is
    resolved from `Settings.agent_llm_provider` -- the one setting that
    changes for a foundation-model swap, alongside the existing
    `openai_api_key`/`openai_base_url`/`openai_chat_model`.
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
    resolved_provider = cfg.resolved_agent_llm_provider()
    return _cached_chat_llm(
        api_key,
        base_url,
        resolved_model,
        round(float(temperature), 4),
        resolved_provider,
        resolved_thinking_enabled,
        resolved_reasoning_effort,
        timeout,
        max_retries,
    )
