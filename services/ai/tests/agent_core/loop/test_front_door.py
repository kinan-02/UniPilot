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


# -- suggested tools -----------------------------------------------------------
#
# `graduation_audit` exhausted at 7 turns on a question `audit_graduation_progress`
# answers in one call: nothing pointed the loop at the composite. The decomposer
# already reads the question, so naming a starting tool costs nothing extra.


async def test_suggested_tools_are_returned_when_they_exist():
    fd = await decompose(
        _FakeAdapter({"sub_asks": ["how many left?"], "suggested_tools": ["audit_graduation_progress"]}),
        "how many required courses are left?",
        temperature=1.0,
        reasoning_effort="low",
        tool_names=frozenset({"audit_graduation_progress", "get_entity"}),
    )
    assert fd.suggested_tools == ["audit_graduation_progress"]


async def test_a_tool_name_the_model_invented_is_dropped():
    """Passing an unknown name through would send the loop hunting for a tool
    that does not exist -- strictly worse than no hint at all."""
    fd = await decompose(
        _FakeAdapter({"sub_asks": ["x"], "suggested_tools": ["check_graduation", "get_entity"]}),
        "q",
        temperature=1.0,
        reasoning_effort="low",
        tool_names=frozenset({"get_entity"}),
    )
    assert fd.suggested_tools == ["get_entity"]


async def test_no_registry_means_no_suggestions():
    fd = await decompose(
        _FakeAdapter({"sub_asks": ["x"], "suggested_tools": ["get_entity"]}),
        "q",
        temperature=1.0,
        reasoning_effort="low",
    )
    assert fd.suggested_tools == []


async def test_malformed_suggested_tools_does_not_break_decomposition():
    fd = await decompose(
        _FakeAdapter({"sub_asks": ["x"], "suggested_tools": "get_entity"}),  # str, not list
        "q",
        temperature=1.0,
        reasoning_effort="low",
        tool_names=frozenset({"get_entity"}),
    )
    assert fd.sub_asks == ["x"]
    assert fd.suggested_tools == []
