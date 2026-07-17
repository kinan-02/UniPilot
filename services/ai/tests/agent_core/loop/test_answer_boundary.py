"""Unit tests for the grounding backstop (resolve_final, §4.2/§9.1). No LLM."""

from __future__ import annotations

from app.agent_core.loop.answer_boundary import resolve_final
from app.agent_core.loop.working_set import Fact


def _facts(**kw: object) -> dict[str, Fact]:
    return {k: Fact(v, "src", "computed", 1.0) for k, v in kw.items()}


def test_slot_filled_number_is_grounded():
    rendered, problems = resolve_final(
        "How many credits remain?",
        _facts(gap=62.5),
        "You still need {gap} credits.",
        {"gap": "gap"},
    )
    assert rendered == "You still need 62.5 credits."
    assert problems == []


def test_bare_number_in_prose_is_rejected():
    rendered, problems = resolve_final(
        "How many credits remain?",
        _facts(gap=62.5),
        "You still need 92.5 credits.",  # typed, not slotted
        {},
    )
    assert "92.5" in problems


def test_number_echoed_from_question_is_allowed():
    rendered, problems = resolve_final(
        "Will I be able to take 00960211?",
        {},
        "Yes, you can take 00960211.",
        {},
    )
    assert problems == []


def test_unresolved_slot_is_flagged():
    _, problems = resolve_final(
        "q",
        {},  # no facts -- the ref binds to nothing
        "You need {gap} credits.",
        {"gap": "gap"},
    )
    assert any(p.startswith("unresolved_slot:") for p in problems)


def test_non_scalar_slot_is_rejected():
    _, problems = resolve_final(
        "q",
        _facts(rec={"grade": 85}),
        "Your record is {rec}.",
        {"rec": "rec"},
    )
    assert any("non-scalar" in p for p in problems)
