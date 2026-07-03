"""Tests for Red-team agent."""

from __future__ import annotations

import pytest

from app.agents.red_team import RedTeamAgent
from app.orchestrator.artifacts import ArbitrationResult, RiskReport
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal


@pytest.mark.asyncio
async def test_red_team_flags_unresolved_preferences() -> None:
    board = Blackboard(
        goal="Plan next semester",
        user_context={"constraints": {}},
        candidate_plan=PlanProposal(course_ids=["00140008"], variant="balanced"),
        open_critiques=[{"type": "day_preference_conflict", "message": "Course meets on Friday."}],
    )
    turn = await RedTeamAgent().run(board)
    assert turn.agent_role == "red_team"
    assert turn.payload["attackCount"] >= 1
    assert turn.payload["reasoningTrace"]["kind"] == "red_team_review"


@pytest.mark.asyncio
async def test_red_team_reports_no_concerns_for_clean_plan() -> None:
    board = Blackboard(
        goal="Plan next semester",
        user_context={"constraints": {"maxCredits": 20}},
        candidate_plan=PlanProposal(
            course_ids=["00140008", "00140102"],
            variant="balanced",
        ),
        risk_report=RiskReport(ok=True, evidence={}),
        arbitration=ArbitrationResult(chosen_variant="balanced", utility=0.8),
    )
    turn = await RedTeamAgent().run(board)
    assert turn.payload["severity"] in {"none", "low"}
