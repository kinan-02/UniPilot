"""End-to-end tests for the agent loop, scripted with a FAKE adapter (no live
LLM) over a stub tool registry. Proves the loop wiring: decompose -> fetch ->
surface -> compute -> final_answer -> grounding backstop -> completeness gate,
plus the governors (completeness rejection continuation, no-progress cap).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

import app.agent_core.loop.runner as runner
from app.agent_core.loop.runner import run_agent_loop
from app.agent_core.planning.state import CertaintyTag
from app.agent_core.tools.envelope import ToolOutputEnvelope
from app.agent_core.tools.registry import ToolDescriptor, ToolRegistry

_COMPLETED = [
    {"courseNumber": "00940224", "creditsEarned": 3.5, "grade": 85},
    {"courseNumber": "00960211", "creditsEarned": 4.0, "grade": 90},
    {"courseNumber": "00110001", "creditsEarned": 2.0, "grade": 70},
]


# -- stub registry ------------------------------------------------------------
class _StubEntityInput(BaseModel):
    entity_type: str = ""
    entity_id: str = ""


async def _stub_get_entity(payload: _StubEntityInput) -> ToolOutputEnvelope:
    return ToolOutputEnvelope(
        ok=True,
        data={"completedCourses": _COMPLETED},
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
    )


def _stub_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDescriptor(
            name="get_entity",
            description="stub fetch",
            input_model=_StubEntityInput,
            output_model=ToolOutputEnvelope,
            side_effect="read",
            callable=_stub_get_entity,
        )
    )
    return registry


# -- fake adapter -------------------------------------------------------------
class _FakeAdapter:
    """Dispatches on the system prompt: decompose / completeness / loop-turn.
    Loop-turn responses are consumed from a queue in order."""

    def __init__(
        self,
        turns: list[dict[str, Any]],
        *,
        sub_asks: list[str],
        completeness: list[dict[str, Any]] | None = None,
    ) -> None:
        self._turns = list(turns)
        self._sub_asks = sub_asks
        self._completeness = list(completeness or [])
        self.gate_calls = 0

    async def complete_json(self, *, system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
        if "break a Technion student's question" in system_prompt:
            resp: dict[str, Any] = {"sub_asks": self._sub_asks}
        elif "verify whether a DRAFT answer" in system_prompt:
            self.gate_calls += 1
            resp = self._completeness.pop(0) if self._completeness else {"unaddressed": []}
        else:
            resp = self._turns.pop(0)
        raw = kwargs.get("raw_model_text_out")
        if raw is not None:
            raw.append(json.dumps(resp))
        return resp


def _install(monkeypatch, adapter: _FakeAdapter) -> None:
    monkeypatch.setattr(runner, "ChatLLMAdapter", lambda: adapter)


_FETCH = {"tool": "get_entity", "arguments": {"entity_type": "completed_courses", "entity_id": "u1"}}
_SURFACE = {"tool": "surface_fact", "arguments": {"key": "completed", "from": "call_1", "path": "data.completedCourses"}}
_COMPUTE = {"tool": "compute", "arguments": {"key": "earned", "expression": {"op": "sum", "of": {"ref": "completed"}, "field": "creditsEarned"}}}
_ANSWER = {"tool": "final_answer", "arguments": {"prose": "You have earned {earned} credits.", "fact_refs": {"earned": "earned"}}}


async def test_happy_path_fetch_surface_compute_answer(monkeypatch):
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "answer", "tool_calls": [_ANSWER]}],
        sub_asks=["How many credits has the student earned so far?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned so far?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert result.ungrounded_numbers == []
    assert result.facts["earned"].value == 9.5
    assert result.facts["earned"].basis == "computed"


async def test_grounding_backstop_rejects_bare_number_then_recovers(monkeypatch):
    bad_answer = {"tool": "final_answer", "arguments": {"prose": "You have earned 999 credits.", "fact_refs": {}}}
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "bad answer", "tool_calls": [bad_answer]},
               {"thought": "good answer", "tool_calls": [_ANSWER]}],
        sub_asks=["earned?"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert result.answer == "You have earned 9.5 credits."
    assert any(step.get("rejected_ungrounded") == ["999"] for step in result.transcript)


async def test_completeness_gate_rejection_continues_the_loop(monkeypatch):
    adapter = _FakeAdapter(
        turns=[{"thought": "fetch", "tool_calls": [_FETCH]},
               {"thought": "surface", "tool_calls": [_SURFACE]},
               {"thought": "compute", "tool_calls": [_COMPUTE]},
               {"thought": "answer1", "tool_calls": [_ANSWER]},
               {"thought": "answer2", "tool_calls": [_ANSWER]}],
        sub_asks=["earned?"],
        completeness=[{"unaddressed": ["earned?"]}, {"unaddressed": []}],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("How many credits have I earned?", "u1", _stub_registry())

    assert result.outcome == "answered"
    assert adapter.gate_calls == 2
    assert any(step.get("completeness_rejected") for step in result.transcript)


async def test_no_progress_governor_forces_graceful_conclusion(monkeypatch):
    noop = {"tool": "surface_fact", "arguments": {"key": "x", "from": "call_9", "path": "nope"}}
    adapter = _FakeAdapter(
        turns=[{"thought": "noop", "tool_calls": [noop]} for _ in range(runner.NO_PROGRESS_LIMIT + 2)],
        sub_asks=["unanswerable"],
    )
    _install(monkeypatch, adapter)

    result = await run_agent_loop("q", "u1", _stub_registry())

    assert result.outcome == "budget_exhausted"
    assert "wasn't able to fully resolve" in result.answer
    assert result.turns == runner.NO_PROGRESS_LIMIT
