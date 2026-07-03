"""Unit tests for Goal Analyst."""

from __future__ import annotations

import pytest

from app.agents.goal_analyst import GoalAnalystAgent
from app.llm.goal_analyst_layer import analyze_goal_deterministic
from app.orchestrator.artifacts import GoalIntent
from app.orchestrator.blackboard import Blackboard


def test_analyze_goal_deterministic_explicit_course() -> None:
    spec = analyze_goal_deterministic(
        "Plan course 00140008 for next semester",
        {"constraints": {"avoidDays": ["שישי"]}},
    )
    assert spec.intent == GoalIntent.EXPLICIT_COURSES
    assert "00140008" in spec.explicit_course_ids


def test_analyze_goal_deterministic_what_if_fail() -> None:
    spec = analyze_goal_deterministic(
        "What if I fail course 00940139?",
        {},
    )
    assert spec.intent == GoalIntent.WHAT_IF_FAIL
    assert "00940139" in spec.explicit_course_ids


def test_analyze_goal_deterministic_what_if_light_load() -> None:
    spec = analyze_goal_deterministic("What if I take a lighter load next semester?", {})
    assert spec.intent == GoalIntent.WHAT_IF
    assert spec.what_if_scenario == "light_load"


@pytest.mark.asyncio
async def test_goal_analyst_agent_records_goal_spec() -> None:
    board = Blackboard(goal="Plan course 00940139 for next semester")
    turn = await GoalAnalystAgent().run(board)

    assert board.goal_spec is not None
    assert turn.agent_role == "goal_analyst"
    assert board.goal_spec.intent == GoalIntent.EXPLICIT_COURSES
