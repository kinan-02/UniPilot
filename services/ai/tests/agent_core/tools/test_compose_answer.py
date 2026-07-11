"""Unit tests for `compose_answer` (docs/agent/AGENT_VISION.md §5, primitive 9a).

Implemented standalone per explicit user instruction -- does not touch
`agent_core.synthesis.synthesis.compose_answer`. No real LLM call is ever
made (same `_FakeLLMAdapter` pattern as test_interpret_text.py).
"""

from __future__ import annotations

import json
from typing import Any

from app.agent_core.tools.primitives.compose_answer import ComposeAnswerInput, run_compose_answer


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
        timeout: float | None = None,
        max_retries: int | None = None,
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
    import app.agent_core.tools.primitives.compose_answer as module

    monkeypatch.setattr(module, "ChatLLMAdapter", lambda: adapter)


_OFFICIAL_FACT = {
    "data": {"courseNumber": "00440105", "credits": 4},
    "certainty": {"basis": "official_record", "confidence": 1.0},
}
_PREDICTED_FACT = {
    "data": {"termPatterns": {"3": "never"}},
    "certainty": {"basis": "predicted_pattern", "confidence": 0.7},
}


async def test_empty_facts_fails_closed():
    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[]))
    assert result.ok is False
    assert "facts_required" in result.error


async def test_fact_missing_data_fails_closed():
    result = await run_compose_answer(
        ComposeAnswerInput(facts_with_certainty=[{"certainty": {"basis": "official_record", "confidence": 1.0}}])
    )
    assert result.ok is False
    assert "fact_0_missing_data" in result.error


async def test_fact_missing_certainty_fails_closed():
    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[{"data": {"x": 1}}]))
    assert result.ok is False
    assert "fact_0_missing_or_invalid_certainty" in result.error


async def test_fact_invalid_certainty_basis_fails_closed():
    result = await run_compose_answer(
        ComposeAnswerInput(
            facts_with_certainty=[{"data": {"x": 1}, "certainty": {"basis": "vibes", "confidence": 1.0}}]
        )
    )
    assert result.ok is False
    assert "fact_0_missing_or_invalid_certainty" in result.error


async def test_fact_invalid_confidence_range_fails_closed():
    """Valid basis, but `confidence=5.0` fails `CertaintyTag`'s own `ge=0,
    le=1` constraint -- caught during `_InterpretedFact.model_validate`."""
    result = await run_compose_answer(
        ComposeAnswerInput(
            facts_with_certainty=[{"data": {"x": 1}, "certainty": {"basis": "official_record", "confidence": 5.0}}]
        )
    )
    assert result.ok is False
    assert "fact_0_invalid_shape" in result.error


async def test_second_fact_error_reports_correct_index():
    result = await run_compose_answer(
        ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT, {"data": {"x": 1}}])
    )
    assert result.ok is False
    assert "fact_1_missing_or_invalid_certainty" in result.error


async def test_llm_unavailable_fails_closed(monkeypatch):
    _patch_llm_adapter(monkeypatch, _UnavailableLLMAdapter())
    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is False
    assert "llm_unavailable" in result.error


async def test_successful_composition_single_fact(monkeypatch):
    fake = _FakeLLMAdapter([{"answer_text": "You have completed 00440105 (4 credits)."}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is True
    assert result.data["answerText"] == "You have completed 00440105 (4 credits)."
    assert result.data["factCount"] == 1
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0
    assert len(fake.calls) == 1


async def test_certainty_aggregation_same_basis_uses_min_confidence(monkeypatch):
    fact_a = {"data": {"a": 1}, "certainty": {"basis": "official_record", "confidence": 1.0}}
    fact_b = {"data": {"b": 2}, "certainty": {"basis": "official_record", "confidence": 0.6}}
    fake = _FakeLLMAdapter([{"answer_text": "composed"}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[fact_a, fact_b]))
    assert result.ok is True
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 0.6


async def test_certainty_aggregation_mixed_basis_falls_back_to_llm_interpretation(monkeypatch):
    fake = _FakeLLMAdapter([{"answer_text": "composed"}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(
        ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT, _PREDICTED_FACT])
    )
    assert result.ok is True
    assert result.certainty.basis == "llm_interpretation"
    assert result.certainty.confidence == 0.7  # min(1.0, 0.7)


async def test_schema_invalid_then_repaired_succeeds(monkeypatch):
    fake = _FakeLLMAdapter([{"wrong_key": "oops"}, {"answer_text": "repaired"}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is True
    assert result.data["answerText"] == "repaired"
    assert len(fake.calls) == 2


async def test_schema_invalid_and_repair_exhausted_fails_closed(monkeypatch):
    fake = _FakeLLMAdapter([{"wrong_key": "a"}, {"wrong_key": "b"}, {"wrong_key": "c"}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is False
    assert "composition_failed" in result.error


async def test_empty_answer_text_fails_closed(monkeypatch):
    fake = _FakeLLMAdapter([{"answer_text": "   "}])
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is False
    assert "composition_failed" in result.error


async def test_llm_call_raises_fails_closed(monkeypatch):
    class _RaisingAdapter:
        def is_available(self) -> bool:
            return True

        async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("network blip")

    _patch_llm_adapter(monkeypatch, _RaisingAdapter())
    result = await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT]))
    assert result.ok is False
    assert "composition_failed" in result.error


async def test_facts_are_sent_to_the_llm(monkeypatch):
    fake = _FakeLLMAdapter([{"answer_text": "composed"}])
    _patch_llm_adapter(monkeypatch, fake)

    await run_compose_answer(ComposeAnswerInput(facts_with_certainty=[_OFFICIAL_FACT, _PREDICTED_FACT]))
    sent_payload = json.loads(fake.calls[0]["user_prompt"])
    assert len(sent_payload["facts"]) == 2
    assert sent_payload["facts"][0]["data"]["courseNumber"] == "00440105"
