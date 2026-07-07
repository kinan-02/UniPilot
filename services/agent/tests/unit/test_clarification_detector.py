"""Unit tests for clarification detector (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.detector import needs_from_missing_context, needs_from_monitor_output


def test_monitor_ask_clarification_creates_need() -> None:
    needs = needs_from_monitor_output(
        {
            "planId": "plan-1",
            "decision": {
                "action": "ask_clarification",
                "clarificationNeeded": True,
                "reason": "missing_preference_context",
            },
        }
    )
    assert len(needs) == 1
    assert needs[0].source == "monitor"
    assert needs[0].ambiguity_type == "preference"


def test_preference_missing_context_creates_preference_need() -> None:
    needs = needs_from_missing_context(
        missing_context=["user preference: prioritize workload or requirements"],
        source="planner",
    )
    assert len(needs) == 1
    assert needs[0].ambiguity_type == "preference"


def test_epistemic_missing_context_creates_epistemic_need() -> None:
    needs = needs_from_missing_context(
        missing_context=["catalog requirement details for track"],
        source="planner",
    )
    assert len(needs) == 1
    assert needs[0].ambiguity_type == "epistemic"
    assert needs[0].evidence.get("retrievableEpistemic") is True


def test_malformed_monitor_output_never_raises() -> None:
    assert needs_from_monitor_output({"decision": "bad"}) == []
    assert needs_from_monitor_output(None) == []  # type: ignore[arg-type]


def test_no_explicit_ambiguity_returns_empty_list() -> None:
    needs = needs_from_missing_context(
        missing_context=["", "   "],
        source="planner",
    )
    assert needs == []
