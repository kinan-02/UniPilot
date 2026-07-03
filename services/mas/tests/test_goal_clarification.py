"""Unit tests for goal clarification gate."""

from __future__ import annotations

import pytest

from app.orchestrator.artifacts import GoalIntent, GoalSpec
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.engine import run_negotiation


@pytest.mark.asyncio
async def test_run_negotiation_awaits_clarification_for_unclear_goal(tmp_path, monkeypatch) -> None:
    from tests.test_orchestrator import _build_engine

    engine = _build_engine(tmp_path)

    class _Settings:
        mas_max_negotiation_rounds = 3

        def llm_configured(self) -> bool:
            return False

    async def _fake_goal_analyst_run(self, blackboard: Blackboard):
        blackboard.goal_spec = GoalSpec(
            intent=GoalIntent.UNCLEAR,
            confidence=0.2,
            clarification_question="Which courses do you want?",
            raw_goal=blackboard.goal,
        )
        from app.orchestrator.types import AgentTurn

        return AgentTurn(
            agent_role="goal_analyst",
            action="critique",
            payload=blackboard.goal_spec.model_dump(),
            rationale="unclear",
        )

    monkeypatch.setattr(
        "app.agents.goal_analyst.GoalAnalystAgent.run",
        _fake_goal_analyst_run,
    )
    monkeypatch.setattr(
        "app.orchestrator.workflow.planning.graph_registry.get_engine",
        lambda *_args, **_kwargs: engine,
    )
    monkeypatch.setattr("app.orchestrator.workflow.planning.get_settings", lambda: _Settings())

    result = await run_negotiation(
        goal="help",
        user_context={},
        settings=_Settings(),
    )

    assert result.status == "awaiting_clarification"
    assert result.final_decision is not None
    assert result.final_decision["clarificationQuestion"] == "Which courses do you want?"
    assert len(result.transcript) == 1
