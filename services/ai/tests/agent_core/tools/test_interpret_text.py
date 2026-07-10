"""Unit tests for `interpret_text` (docs/agent/AGENT_VISION.md §5, primitive 4).

No real LLM call is ever made -- a local `_FakeLLMAdapter` (same
queued-response pattern as `tests/agent_core/conftest.py`'s own
`FakeLLMAdapter`, plus `is_available()` since `run_interpret_text`
constructs its own `ChatLLMAdapter()` internally rather than taking one as a
parameter) is injected by monkeypatching the module's `ChatLLMAdapter` name.

Real-data case uses `use_real_academic_engine` and the verified-real wiki
page "student-rights" (already used in test_get_entity.py).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agent_core.tools.primitives.interpret_text import InterpretTextInput, run_interpret_text


class _FakeLLMAdapter:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

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
    ) -> dict[str, Any]:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        if not self._responses:
            raise AssertionError("_FakeLLMAdapter exhausted its queued responses")
        response = self._responses.pop(0)
        if raw_model_text_out is not None:
            raw_model_text_out.append(json.dumps(response))
        return response


class _UnavailableLLMAdapter:
    def is_available(self) -> bool:
        return False


def _patch_llm_adapter(monkeypatch, adapter):
    import app.agent_core.tools.primitives.interpret_text as module

    monkeypatch.setattr(module, "ChatLLMAdapter", lambda: adapter)


async def test_empty_source_fails_closed():
    result = await run_interpret_text(InterpretTextInput(source="  ", question="what is the retake limit?"))
    assert result.ok is False
    assert "source_required" in result.error


async def test_empty_question_fails_closed():
    result = await run_interpret_text(InterpretTextInput(source="student-rights", question=" "))
    assert result.ok is False
    assert "question_required" in result.error


async def test_source_not_found_fails_closed(use_real_academic_engine):
    result = await run_interpret_text(
        InterpretTextInput(source="does-not-exist-slug", question="anything")
    )
    assert result.ok is False
    assert "source_not_found: does-not-exist-slug" in result.error


async def test_llm_unavailable_fails_closed(use_real_academic_engine, monkeypatch):
    _patch_llm_adapter(monkeypatch, _UnavailableLLMAdapter())
    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    assert result.ok is False
    assert "llm_unavailable" in result.error


async def test_determined_interpretation_succeeds(use_real_academic_engine, monkeypatch):
    fake = _FakeLLMAdapter(
        [{"status": "determined", "answer": "Students may appeal within 4 days.", "cited_section": "5.4 Grade Appeal", "confidence": 0.9}]
    )
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_interpret_text(
        InterpretTextInput(source="student-rights", question="How long do students have to appeal a grade?")
    )
    assert result.ok is True
    assert result.data["answer"] == "Students may appeal within 4 days."
    assert result.data["citedSection"] == "5.4 Grade Appeal"
    assert result.data["source"] == "student-rights"
    assert result.certainty.basis == "llm_interpretation"
    assert result.certainty.confidence == 0.9
    assert result.certainty.source_ref.page == "student-rights"
    assert result.certainty.source_ref.section == "5.4 Grade Appeal"
    # The real wiki content was actually sent to the "LLM".
    assert len(fake.calls) == 1
    assert "student-rights" in fake.calls[0]["user_prompt"]


async def test_model_reports_cannot_determine(use_real_academic_engine, monkeypatch):
    fake = _FakeLLMAdapter([{"status": "cannot_determine", "answer": None, "cited_section": None, "confidence": 0.0}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="unanswerable question"))
    assert result.ok is False
    assert "cannot_determine" in result.error


async def test_determined_status_without_real_citation_fails_closed(use_real_academic_engine, monkeypatch):
    """Schema-valid but semantically hollow -- status='determined' with a
    null/empty cited_section must still fail closed, never be trusted."""
    fake = _FakeLLMAdapter([{"status": "determined", "answer": "some answer", "cited_section": None, "confidence": 0.8}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    assert result.ok is False
    assert "cannot_determine" in result.error


async def test_schema_invalid_then_repaired_succeeds(use_real_academic_engine, monkeypatch):
    fake = _FakeLLMAdapter(
        [
            {"status": "determined"},  # missing required fields -- triggers repair
            {"status": "determined", "answer": "repaired answer", "cited_section": "Intro", "confidence": 0.7},
        ]
    )
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    assert result.ok is True
    assert result.data["answer"] == "repaired answer"
    assert len(fake.calls) == 2


async def test_schema_invalid_and_repair_exhausted_fails_closed(use_real_academic_engine, monkeypatch):
    fake = _FakeLLMAdapter([{"status": "determined"}, {"status": "determined"}, {"status": "determined"}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    assert result.ok is False
    assert "cannot_determine" in result.error


async def test_llm_call_raises_fails_closed(use_real_academic_engine, monkeypatch):
    class _RaisingAdapter:
        def is_available(self) -> bool:
            return True

        async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("network blip")

    _patch_llm_adapter(monkeypatch, _RaisingAdapter())
    result = await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    assert result.ok is False
    assert "cannot_determine" in result.error


def test_to_output_clamps_out_of_range_confidence():
    """The JSON schema itself already bounds `confidence` to [0, 1], so an
    out-of-range value from the LLM is caught by schema validation (and
    routed into the repair loop) before `_to_output` ever sees it -- this
    directly unit-tests `_to_output`'s own clamp as defense-in-depth for a
    value that somehow reaches it anyway (e.g. a future schema-repair path
    that substitutes a value without re-validating range)."""
    from app.agent_core.tools.primitives.interpret_text import InterpretTextReasoningBlock

    block = InterpretTextReasoningBlock(llm_adapter=_FakeLLMAdapter([]))
    output = block._to_output({"status": "determined", "answer": "x", "cited_section": "y", "confidence": 5.0})
    assert output.determined is True
    assert output.confidence == 1.0


def test_to_output_defaults_non_numeric_confidence_to_zero():
    from app.agent_core.tools.primitives.interpret_text import InterpretTextReasoningBlock

    block = InterpretTextReasoningBlock(llm_adapter=_FakeLLMAdapter([]))
    output = block._to_output({"status": "determined", "answer": "x", "cited_section": "y", "confidence": "high"})
    assert output.determined is True
    assert output.confidence == 0.0


async def test_source_content_is_truncated(use_real_academic_engine, monkeypatch):
    from app.agent_core.tools.primitives.interpret_text import _MAX_SOURCE_CHARS

    fake = _FakeLLMAdapter([{"status": "determined", "answer": "x", "cited_section": "y", "confidence": 0.5}])
    _patch_llm_adapter(monkeypatch, fake)

    await run_interpret_text(InterpretTextInput(source="student-rights", question="anything"))
    sent_payload = json.loads(fake.calls[0]["user_prompt"])
    assert len(sent_payload["source_text"]) <= _MAX_SOURCE_CHARS
