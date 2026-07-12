"""Unit tests for `get_policy_answer` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Composes real `search_knowledge` (against the real wiki, via
`use_real_academic_engine`) with `interpret_text` driven by a fake LLM
adapter (same pattern as test_interpret_text.py) -- no real LLM call is
ever made. "student rights ombudsman" ranking "student-rights" as its top
match is reused from test_search_knowledge.py's own verified fact.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent_core.tools.composites.get_policy_answer import (
    GetPolicyAnswerInput,
    _distinct_slugs_in_rank_order,
    run_get_policy_answer,
)


class _FakeLLMAdapter:
    """Queued responses are consumed in order across however many
    `interpret_text` calls `get_policy_answer` makes internally -- lets a
    single fake drive a multi-candidate fallback sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

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
        streaming_queue: asyncio.Queue[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(user_prompt)
        if not self._responses:
            raise AssertionError("_FakeLLMAdapter exhausted its queued responses")
        response = self._responses.pop(0)
        if raw_model_text_out is not None:
            raw_model_text_out.append(json.dumps(response))
        return response


def _patch_interpret_text_llm(monkeypatch, adapter):
    import app.agent_core.tools.primitives.interpret_text as module

    monkeypatch.setattr(module, "ChatLLMAdapter", lambda: adapter)


async def test_empty_question_fails_closed():
    result = await run_get_policy_answer(GetPolicyAnswerInput(question="  "))
    assert result.ok is False
    assert "question_required" in result.error


async def test_search_failure_propagates(monkeypatch):
    import app.agent_core.tools.composites.get_policy_answer as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_not_configured")

    monkeypatch.setattr(module, "run_search_knowledge", _fake_search)
    result = await run_get_policy_answer(GetPolicyAnswerInput(question="anything"))
    assert result.ok is False
    assert "search_failed: academic_graph_not_configured" in result.error


async def test_no_relevant_source_found(monkeypatch):
    import app.agent_core.tools.composites.get_policy_answer as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"query": "x", "matches": []})

    monkeypatch.setattr(module, "run_search_knowledge", _fake_search)
    result = await run_get_policy_answer(GetPolicyAnswerInput(question="anything"))
    assert result.ok is False
    assert "no_relevant_source_found" in result.error


async def test_answers_from_top_ranked_source(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.get_policy_answer as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"query": "x", "matches": [{"slug": "student-rights", "score": 1.0}]})
    monkeypatch.setattr(module, "run_search_knowledge", _fake_search)

    fake = _FakeLLMAdapter(
        [{"status": "determined", "answer": "4 days", "cited_section": "5.4 Grade Appeal", "confidence": 0.9}]
    )
    _patch_interpret_text_llm(monkeypatch, fake)

    result = await run_get_policy_answer(
        GetPolicyAnswerInput(question="How long do students have to appeal a grade?")
    )
    assert result.ok is True
    assert result.data["answer"] == "4 days"
    assert result.data["citedSection"] == "5.4 Grade Appeal"
    assert result.data["source"] == "student-rights"
    assert result.data["sourcesConsidered"] == ["student-rights"]
    assert result.certainty.basis == "llm_interpretation"
    assert result.certainty.confidence == 0.9
    assert len(fake.calls) == 1


async def test_falls_back_to_next_candidate_when_first_is_undetermined(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.get_policy_answer as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"query": "x", "matches": [{"slug": "regulations-undergraduate"}, {"slug": "student-rights"}]})
    monkeypatch.setattr(module, "run_search_knowledge", _fake_search)

    fake = _FakeLLMAdapter(
        [
            {"status": "cannot_determine", "answer": None, "cited_section": None, "confidence": 0.0},
            {"status": "determined", "answer": "found it", "cited_section": "Somewhere", "confidence": 0.6},
        ]
    )
    _patch_interpret_text_llm(monkeypatch, fake)

    result = await run_get_policy_answer(GetPolicyAnswerInput(question="student rights ombudsman"))
    assert result.ok is True
    assert result.data["answer"] == "found it"
    assert len(result.data["sourcesConsidered"]) == 2
    assert result.data["source"] == result.data["sourcesConsidered"][-1]
    assert len(fake.calls) == 2


async def test_cannot_determine_when_every_candidate_fails(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.get_policy_answer as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"query": "x", "matches": [{"slug": "regulations-undergraduate"}, {"slug": "student-rights"}, {"slug": "faculty-mathematics"}]})
    monkeypatch.setattr(module, "run_search_knowledge", _fake_search)

    fake = _FakeLLMAdapter(
        [
            {"status": "cannot_determine", "answer": None, "cited_section": None, "confidence": 0.0}
            for _ in range(3)
        ]
    )
    _patch_interpret_text_llm(monkeypatch, fake)

    result = await run_get_policy_answer(GetPolicyAnswerInput(question="student rights ombudsman"))
    assert result.ok is False
    assert "cannot_determine" in result.error
    assert len(fake.calls) == 3  # bounded by _MAX_SOURCES_TRIED, never unbounded


# -- _distinct_slugs_in_rank_order -------------------------------------


def test_distinct_slugs_dedupes_preserving_rank_order():
    matches = [
        {"slug": "a", "score": 0.9},
        {"slug": "b", "score": 0.8},
        {"slug": "a", "score": 0.7},
        {"slug": "c", "score": 0.6},
    ]
    assert _distinct_slugs_in_rank_order(matches) == ["a", "b", "c"]


def test_distinct_slugs_skips_missing_slug():
    matches = [{"slug": None}, {"slug": "a"}, {}]
    assert _distinct_slugs_in_rank_order(matches) == ["a"]
