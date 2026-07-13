"""Unit tests for `get_current_semester` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Bundles `get_current_date` (pure, no LLM) with `interpret_text` (reads the
real academic calendar wiki page) -- `interpret_text` constructs its own
`ChatLLMAdapter()` internally, so it's mocked the same way
`test_interpret_text.py` does: monkeypatching `ChatLLMAdapter` on the
`interpret_text` module (where `get_current_semester` actually calls
`run_interpret_text`, not where it's imported from).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.agent_core.tools.composites.get_current_semester import (
    GetCurrentSemesterInput,
    run_get_current_semester,
)


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
        streaming_queue: asyncio.Queue[str] | None = None,
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


async def test_returns_both_current_and_next_semester_as_distinct_fields(use_real_academic_engine, monkeypatch):
    # Regression guard: a live-eval run found a step's success_criteria
    # routinely expecting BOTH a current and a next semester as distinct
    # values -- a single free-text answer covering both didn't parse into
    # two clean fields, so a genuinely correct tool call still failed its
    # success-check and triggered a wasted re-plan, twice.
    fake = _FakeLLMAdapter(
        [
            {
                "status": "determined",
                "answer": "Winter 2025/2026",
                "cited_section": "Undergraduate School",
                "confidence": 0.9,
            },
            {
                "status": "determined",
                "answer": "Spring 2025/2026",
                "cited_section": "Undergraduate School",
                "confidence": 0.9,
            },
        ]
    )
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_get_current_semester(GetCurrentSemesterInput())

    assert result.ok is True
    today = datetime.now(timezone.utc).date().isoformat()
    assert result.data["today"] == today
    assert result.data["currentSemester"] == "Winter 2025/2026"
    assert result.data["nextSemester"] == "Spring 2025/2026"
    # The machine YYYY-S codes are derived deterministically from the prose
    # names (Winter=1, Spring=2, academic year = the first 4-digit year) --
    # a live-eval run found the Planner otherwise adding an unsatisfiable
    # "convert the name into a YYYY-S code" step and looping until timeout.
    assert result.data["currentSemesterCode"] == "2025-1"
    assert result.data["nextSemesterCode"] == "2025-2"
    assert result.certainty.basis == "llm_interpretation"
    # Today's actual date must have reached both interpretation prompts --
    # never a stale or fabricated one.
    assert len(fake.calls) == 2
    assert today in fake.calls[0]["user_prompt"]
    assert today in fake.calls[1]["user_prompt"]


async def test_between_semesters_current_is_none_but_next_still_resolves(use_real_academic_engine, monkeypatch):
    fake = _FakeLLMAdapter(
        [
            {"status": "determined", "answer": "none", "cited_section": "Undergraduate School", "confidence": 0.8},
            {
                "status": "determined",
                "answer": "Spring 2025/2026",
                "cited_section": "Undergraduate School",
                "confidence": 0.9,
            },
        ]
    )
    _patch_llm_adapter(monkeypatch, fake)

    result = await run_get_current_semester(GetCurrentSemesterInput())

    assert result.ok is True
    assert result.data["currentSemester"] == "none"
    assert result.data["nextSemester"] == "Spring 2025/2026"
    # "none" has no season/year to parse -> code is None, not fabricated.
    assert result.data["currentSemesterCode"] is None
    assert result.data["nextSemesterCode"] == "2025-2"


async def test_cannot_determine_either_fails_closed(use_real_academic_engine, monkeypatch):
    _patch_llm_adapter(monkeypatch, _UnavailableLLMAdapter())

    result = await run_get_current_semester(GetCurrentSemesterInput())

    assert result.ok is False
    assert "could_not_determine_semester" in result.error


async def test_takes_no_arguments():
    schema = GetCurrentSemesterInput.model_json_schema()
    assert schema.get("required", []) == []


def test_semester_name_to_code_parses_english_hebrew_and_all_three_terms():
    from app.agent_core.tools.composites.get_current_semester import _semester_name_to_code

    assert _semester_name_to_code("Winter 2025/2026") == "2025-1"
    assert _semester_name_to_code("Spring Semester 2025/2026") == "2025-2"
    assert _semester_name_to_code("Summer 2025/2026") == "2025-3"
    assert _semester_name_to_code("סמסטר קיץ 2025/2026") == "2025-3"
    # Unparseable / absent inputs never fabricate a code.
    assert _semester_name_to_code("none") is None
    assert _semester_name_to_code(None) is None
    assert _semester_name_to_code("Spring") is None  # no year
