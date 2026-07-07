"""Unit tests for `ChatLLMAdapter`, including the flag-gated structured-output path."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError
from app.config import Settings

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatModel:
    """Stands in for the object `build_chat_llm` would normally return."""

    def __init__(self, *, free_text_response: str = '{"answer": "ok"}') -> None:
        self._free_text_response = free_text_response
        self.with_structured_output_calls: list[dict[str, Any]] = []
        self._structured_result: Any = {"parsed": {"answer": "structured"}, "raw": _FakeMessage("raw text")}
        self._structured_raises = False

    async def ainvoke(self, messages: list[Any]) -> _FakeMessage:
        return _FakeMessage(self._free_text_response)

    def with_structured_output(self, schema: dict[str, Any], *, include_raw: bool = False) -> "_FakeStructuredRunnable":
        self.with_structured_output_calls.append({"schema": schema, "include_raw": include_raw})
        return _FakeStructuredRunnable(self)


class _FakeStructuredRunnable:
    def __init__(self, parent: _FakeChatModel) -> None:
        self._parent = parent

    async def ainvoke(self, messages: list[Any]) -> Any:
        if self._parent._structured_raises:
            raise RuntimeError("provider does not support structured output")
        return self._parent._structured_result


def _settings(*, structured_output_enabled: bool) -> Settings:
    return Settings(
        **{
            "OPENAI_API_KEY": "sk-test",
            "AGENT_REASONING_STRUCTURED_OUTPUT_ENABLED": structured_output_enabled,
        }
    )


@pytest.fixture(autouse=True)
def _clear_client_cache():
    from app.agent import llm_client

    llm_client._cached_chat_llm.cache_clear()
    yield
    llm_client._cached_chat_llm.cache_clear()


async def test_flag_off_uses_free_text_parse_path_even_with_a_schema(monkeypatch):
    fake_model = _FakeChatModel()
    monkeypatch.setattr(
        "app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: fake_model
    )
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=False))

    result = await adapter.complete_json(
        system_prompt="sys", user_prompt="usr", response_schema=_SCHEMA
    )

    assert result == {"answer": "ok"}
    assert fake_model.with_structured_output_calls == []


async def test_flag_on_uses_structured_output_and_returns_parsed_result(monkeypatch):
    fake_model = _FakeChatModel()
    monkeypatch.setattr(
        "app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: fake_model
    )
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=True))
    raw_text_out: list[str] = []

    result = await adapter.complete_json(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=_SCHEMA,
        raw_model_text_out=raw_text_out,
    )

    assert result == {"answer": "structured"}
    assert len(fake_model.with_structured_output_calls) == 1
    assert fake_model.with_structured_output_calls[0]["schema"] == _SCHEMA
    assert raw_text_out == ["raw text"]


async def test_flag_on_but_no_response_schema_never_calls_structured_output(monkeypatch):
    fake_model = _FakeChatModel()
    monkeypatch.setattr(
        "app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: fake_model
    )
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=True))

    result = await adapter.complete_json(system_prompt="sys", user_prompt="usr", response_schema=None)

    assert result == {"answer": "ok"}
    assert fake_model.with_structured_output_calls == []


async def test_structured_output_error_falls_back_to_free_text_path(monkeypatch):
    fake_model = _FakeChatModel()
    fake_model._structured_raises = True
    monkeypatch.setattr(
        "app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: fake_model
    )
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=True))

    result = await adapter.complete_json(
        system_prompt="sys", user_prompt="usr", response_schema=_SCHEMA
    )

    # Falls back to the free-text path's response rather than raising.
    assert result == {"answer": "ok"}


async def test_structured_output_non_dict_parsed_falls_back_to_free_text_path(monkeypatch):
    fake_model = _FakeChatModel()
    fake_model._structured_result = {"parsed": None, "raw": _FakeMessage("raw text")}
    monkeypatch.setattr(
        "app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: fake_model
    )
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=True))

    result = await adapter.complete_json(
        system_prompt="sys", user_prompt="usr", response_schema=_SCHEMA
    )

    assert result == {"answer": "ok"}


async def test_llm_unavailable_still_raises_before_any_structured_output_attempt(monkeypatch):
    monkeypatch.setattr("app.agent.reasoning.llm_adapter.build_chat_llm", lambda **_kwargs: None)
    adapter = ChatLLMAdapter(settings=_settings(structured_output_enabled=True))

    with pytest.raises(LLMAdapterError):
        await adapter.complete_json(system_prompt="sys", user_prompt="usr", response_schema=_SCHEMA)
