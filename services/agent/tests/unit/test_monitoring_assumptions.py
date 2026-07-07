"""Unit tests for monitoring assumption extraction (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.assumptions import (
    assumptions_from_conversation_assumptions,
    assumptions_from_planner_output,
    assumptions_from_task_understanding,
)


def test_planner_assumptions_extracted() -> None:
    assumptions = assumptions_from_planner_output(
        {
            "plan_id": "p1",
            "user_goal": "Graduate on time",
            "execution_mode": "single_capability",
            "assumptions": ["Student is in CS track"],
            "missing_context": ["transcript_summary"],
            "write_risk": "none",
        }
    )
    assert any(item.id == "planner_user_goal" for item in assumptions)
    assert any(item.provenance == "assumed" for item in assumptions)


def test_task_understanding_assumptions_extracted() -> None:
    assumptions = assumptions_from_task_understanding(
        {
            "user_goal": "Check graduation progress",
            "primary_intent": "graduation_progress_check",
            "overall_confidence": 0.8,
            "source": "llm_reasoning_block",
        }
    )
    assert any(item.id == "tu_user_goal" for item in assumptions)


def test_conversation_assumptions_become_provenance_assumed() -> None:
    assumptions = assumptions_from_conversation_assumptions(["Prefers morning classes"])
    assert len(assumptions) == 1
    assert assumptions[0].provenance == "assumed"


def test_deterministic_facts_become_provenance_deterministic() -> None:
    assumptions = assumptions_from_planner_output({"user_goal": "Plan next semester", "execution_mode": "planning"})
    assert all(item.provenance == "deterministic" for item in assumptions if item.id.startswith("planner_"))


def test_empty_input_returns_empty_list() -> None:
    assert assumptions_from_planner_output({}) == []
    assert assumptions_from_task_understanding(None) == []
    assert assumptions_from_conversation_assumptions([]) == []


def test_malformed_input_never_raises() -> None:
    assert assumptions_from_planner_output(None) == []
    assert assumptions_from_task_understanding("bad") == []
