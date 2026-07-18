"""Unit tests for the Front Door scope-gate + decomposition (§8.1). Fake adapter,
no LLM: exercises how `decompose` reads the triage verdict, and that it fails
OPEN so a missing flag never silently declines a legitimate question."""

from __future__ import annotations

from typing import Any

from app.agent_core.loop.front_door import decompose


class _FakeAdapter:
    def __init__(self, resp: dict[str, Any]) -> None:
        self._resp = resp

    async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
        return self._resp


async def test_out_of_scope_question_declines_with_a_reason():
    fd = await decompose(
        _FakeAdapter({"in_scope": False, "decline_reason": "I only help with Technion academics."}),
        "write me a poem",
        temperature=1.0,
        reasoning_effort="medium",
    )
    assert fd.in_scope is False
    assert "Technion academics" in (fd.decline_reason or "")
    assert fd.sub_asks == []


async def test_in_scope_question_returns_its_sub_asks():
    fd = await decompose(
        _FakeAdapter({"in_scope": True, "sub_asks": ["How many credits remain?"]}),
        "how many credits do I have left?",
        temperature=1.0,
        reasoning_effort="medium",
    )
    assert fd.in_scope is True
    assert fd.sub_asks == ["How many credits remain?"]


async def test_missing_in_scope_flag_fails_open_to_answering():
    # Absence of the flag must NEVER decline -- only an explicit false does.
    fd = await decompose(
        _FakeAdapter({"sub_asks": ["x"]}), "q", temperature=1.0, reasoning_effort="medium"
    )
    assert fd.in_scope is True
    assert fd.sub_asks == ["x"]


async def test_decline_without_a_reason_uses_a_default():
    fd = await decompose(
        _FakeAdapter({"in_scope": False}), "q", temperature=1.0, reasoning_effort="medium"
    )
    assert fd.in_scope is False
    assert fd.decline_reason  # a non-empty student-facing default
