"""MAS-3 policy Q&A workflow — regulations RAG without planning negotiation."""

from __future__ import annotations

from typing import Any

from app.agents.goal_analyst import GoalAnalystAgent
from app.agents.policy_responder import PolicyResponderAgent
from app.config import Settings, get_settings
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import NegotiationResult
from app.orchestrator.workflow.snapshot import workflow_snapshot
from app.services.graph_registry import graph_registry


async def run_policy_qa_workflow(
    *,
    goal: str,
    user_context: dict[str, Any],
    settings: Settings | None = None,
    session_id: str | None = None,
    initial_transcript: list[dict[str, Any]] | None = None,
) -> NegotiationResult:
    """Answer regulation/policy questions using wiki-backed retrieval."""
    cfg = settings or get_settings()
    engine = graph_registry.get_engine_for_user_context(user_context, cfg)
    blackboard = Blackboard(
        goal=goal,
        user_context=user_context,
        settings=cfg,
        engine=engine,
        max_rounds=1,
        transcript=list(initial_transcript or []),
        session_id=session_id,
    )

    goal_analyst = GoalAnalystAgent()
    analyst_turn = await goal_analyst.run(blackboard)
    blackboard.record_turn(analyst_turn)
    await workflow_snapshot(blackboard, "goal_analyst")

    policy_responder = PolicyResponderAgent()
    policy_turn = await policy_responder.run(blackboard)
    blackboard.record_turn(policy_turn)
    await workflow_snapshot(blackboard, "policy_responder")

    payload = policy_turn.payload
    return NegotiationResult(
        status="completed",
        final_decision={
            "vertical": "policy_qa",
            "answer": payload.get("answer"),
            "citations": list(payload.get("citations") or []),
            "goalSpec": blackboard.goal_spec.model_dump() if blackboard.goal_spec else None,
        },
        transcript=blackboard.transcript,
        rounds=1,
    )
