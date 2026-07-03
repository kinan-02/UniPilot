"""Goal Analyst agent — parses student goals before negotiation."""

from __future__ import annotations

from app.llm.goal_analyst_layer import analyze_goal_deterministic, analyze_goal_with_llm
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.reasoning_trace import build_goal_analysis_trace


class GoalAnalystAgent:
    role = "goal_analyst"

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        settings = blackboard.settings
        llm_enabled = bool(settings and settings.llm_configured())

        if llm_enabled:
            goal_spec = await analyze_goal_with_llm(
                blackboard.goal,
                blackboard.user_context,
                settings=settings,
            )
        else:
            goal_spec = analyze_goal_deterministic(blackboard.goal, blackboard.user_context)

        blackboard.goal_spec = goal_spec
        goal_payload = goal_spec.model_dump()
        goal_payload["reasoningTrace"] = build_goal_analysis_trace(goal_spec=goal_payload)
        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=goal_payload,
            rationale=(
                f"Goal classified as {goal_spec.intent.value} "
                f"(confidence {goal_spec.confidence:.2f}, source={goal_spec.analysis_source})."
            ),
            references=[
                f"goal:intent={goal_spec.intent.value}",
                f"goal:confidence={goal_spec.confidence}",
                f"goal:source={goal_spec.analysis_source}",
            ],
        )
