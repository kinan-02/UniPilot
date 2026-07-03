"""Unit tests for MAS blackboard state."""

from __future__ import annotations

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn, PlanProposal


def test_blackboard_records_turns_and_tracks_vetoes() -> None:
    board = Blackboard(goal="plan next semester", user_context={"completed_courses": ["00940139"]})
    board.set_candidate(
        PlanProposal(course_ids=["0940345"], semester_filename="courses_2025_201.json")
    )
    board.record_turn(
        AgentTurn(agent_role="planner", action="propose", payload={}, rationale="initial")
    )
    board.apply_veto(
        agent_role="catalog_scout",
        violations=["missing prereq"],
        references=["eligibility:0940345:eligible=False"],
    )

    assert board.completed_courses == ["00940139"]
    assert len(board.transcript) == 1
    assert board.open_vetoes
    assert board.validation_violations == ["missing prereq"]
    assert board.unique_agent_roles() == 1
