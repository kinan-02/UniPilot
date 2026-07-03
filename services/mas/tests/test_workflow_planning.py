"""Tests for planning workflow helpers."""

from __future__ import annotations

import pytest

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.workflow.planning import (
    clarification_question,
    needs_goal_clarification,
)
from app.orchestrator.artifacts import GoalIntent, GoalSpec


def test_needs_goal_clarification_for_unclear_low_confidence_goal() -> None:
    board = Blackboard(
        goal="help me",
        goal_spec=GoalSpec(intent=GoalIntent.UNCLEAR, confidence=0.2),
    )
    assert needs_goal_clarification(board) is True


def test_clarification_question_uses_goal_spec_prompt() -> None:
    board = Blackboard(
        goal="help me",
        goal_spec=GoalSpec(
            intent=GoalIntent.UNCLEAR,
            confidence=0.2,
            clarification_question="Which semester do you mean?",
        ),
    )
    assert clarification_question(board) == "Which semester do you mean?"


def test_clarification_question_falls_back_to_default_prompt() -> None:
    board = Blackboard(
        goal="help me",
        goal_spec=GoalSpec(intent=GoalIntent.UNCLEAR, confidence=0.2),
    )
    question = clarification_question(board)
    assert "clarify" in question.lower()


def test_needs_goal_clarification_false_without_goal_spec() -> None:
    board = Blackboard(goal="plan next semester")
    assert needs_goal_clarification(board) is False
