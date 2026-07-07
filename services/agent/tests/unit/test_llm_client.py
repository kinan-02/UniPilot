"""Unit tests for the shared, cached chat LLM client builder."""

from __future__ import annotations

import asyncio

import pytest

from app.agent import llm_client
from app.config import Settings


class _FakeChatOpenAI:
    """Stand-in for `langchain_openai.ChatOpenAI` that records construction calls."""

    instances_created = 0

    def __init__(self, **kwargs):
        _FakeChatOpenAI.instances_created += 1
        self.kwargs = kwargs


@pytest.fixture(autouse=True)
def _reset_cache_and_counter(monkeypatch):
    """Every test gets a clean LRU cache and construction counter."""
    llm_client._cached_chat_llm.cache_clear()
    _FakeChatOpenAI.instances_created = 0
    monkeypatch.setattr(
        "langchain_openai.ChatOpenAI",
        _FakeChatOpenAI,
        raising=False,
    )
    yield
    llm_client._cached_chat_llm.cache_clear()


def _settings(**overrides) -> Settings:
    defaults = {
        "OPENAI_API_KEY": "sk-test-key",
        "OPENAI_CHAT_MODEL": "gpt-4o-mini",
        "OPENAI_BASE_URL": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_identical_params_return_the_same_cached_client():
    settings = _settings()

    first = llm_client.build_chat_llm(settings=settings, temperature=0.1)
    second = llm_client.build_chat_llm(settings=settings, temperature=0.1)

    assert first is second
    assert _FakeChatOpenAI.instances_created == 1


def test_different_temperature_produces_distinct_clients():
    settings = _settings()

    first = llm_client.build_chat_llm(settings=settings, temperature=0.1)
    second = llm_client.build_chat_llm(settings=settings, temperature=0.2)

    assert first is not second
    assert _FakeChatOpenAI.instances_created == 2


def test_different_base_url_produces_distinct_clients():
    settings_a = _settings(OPENAI_BASE_URL="https://api-a.example.com")
    settings_b = _settings(OPENAI_BASE_URL="https://api-b.example.com")

    first = llm_client.build_chat_llm(settings=settings_a, temperature=0.0)
    second = llm_client.build_chat_llm(settings=settings_b, temperature=0.0)

    assert first is not second
    assert _FakeChatOpenAI.instances_created == 2


def test_missing_api_key_returns_none_and_never_touches_the_cache():
    settings = _settings(OPENAI_API_KEY=None)

    result = llm_client.build_chat_llm(settings=settings, temperature=0.0)

    assert result is None
    assert _FakeChatOpenAI.instances_created == 0


def test_two_independently_constructed_settings_with_identical_values_share_a_client():
    """Proves the cache key is the resolved primitives, not the `Settings` instance."""
    settings_1 = Settings(**{"OPENAI_API_KEY": "sk-shared", "OPENAI_CHAT_MODEL": "gpt-4o-mini"})
    settings_2 = Settings(**{"OPENAI_API_KEY": "sk-shared", "OPENAI_CHAT_MODEL": "gpt-4o-mini"})
    assert settings_1 is not settings_2

    first = llm_client.build_chat_llm(settings=settings_1, temperature=0.0)
    second = llm_client.build_chat_llm(settings=settings_2, temperature=0.0)

    assert first is second
    assert _FakeChatOpenAI.instances_created == 1


async def test_concurrent_calls_with_identical_params_construct_at_most_once():
    settings = _settings()

    async def _build():
        return llm_client.build_chat_llm(settings=settings, temperature=0.0)

    results = await asyncio.gather(*(_build() for _ in range(20)))

    assert len({id(client) for client in results}) == 1
    assert _FakeChatOpenAI.instances_created == 1
