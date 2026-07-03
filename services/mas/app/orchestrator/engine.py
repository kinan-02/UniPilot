"""Multi-agent negotiation orchestrator for MAS sessions."""

from __future__ import annotations

from typing import Any

from app.agents.registry import AgentRegistry
from app.config import Settings
from app.llm.goal_analyst_layer import analyze_goal_deterministic
from app.orchestrator.artifacts import GoalIntent
from app.orchestrator.types import NegotiationResult
from app.orchestrator.workflow.planning import run_planning_negotiation
from app.orchestrator.workflow.policy import run_policy_qa_workflow


async def run_negotiation(
    *,
    goal: str,
    user_context: dict[str, Any],
    settings: Settings | None = None,
    registry: AgentRegistry | None = None,
    session_id: str | None = None,
    initial_transcript: list[dict[str, Any]] | None = None,
) -> NegotiationResult:
    """Route to planning or policy Q&A workflow based on goal intent."""
    pre_spec = analyze_goal_deterministic(goal, user_context)
    if pre_spec.intent == GoalIntent.POLICY_QA:
        return await run_policy_qa_workflow(
            goal=goal,
            user_context=user_context,
            settings=settings,
            session_id=session_id,
            initial_transcript=initial_transcript,
        )

    return await run_planning_negotiation(
        goal=goal,
        user_context=user_context,
        settings=settings,
        registry=registry,
        session_id=session_id,
        initial_transcript=initial_transcript,
    )
