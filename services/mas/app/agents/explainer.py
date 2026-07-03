"""Explainer agent — post-commit student-facing summary (read-only)."""

from __future__ import annotations

from app.llm.explainer_layer import build_deterministic_summary, explain_decision_with_llm
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn, PlanProposal
from app.services.reasoning_trace import build_explainer_trace


class ExplainerAgent:
    role = "explainer"

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        proposal = blackboard.candidate_plan or PlanProposal()
        final_decision = {
            "course_ids": list(proposal.course_ids),
            "semesterLabel": None,
            "utilityBreakdown": blackboard.utility_breakdown or {},
            "softCritiques": list(blackboard.open_critiques),
        }
        if blackboard.arbitration is not None:
            final_decision["utilityBreakdown"] = blackboard.arbitration.breakdown

        settings = blackboard.settings
        if settings and settings.llm_configured():
            summary = await explain_decision_with_llm(
                goal=blackboard.goal,
                proposal=proposal,
                final_decision=final_decision,
                transcript=blackboard.transcript,
                soft_critiques=blackboard.open_critiques,
                settings=settings,
            )
        else:
            summary = build_deterministic_summary(
                goal=blackboard.goal,
                proposal=proposal,
                final_decision=final_decision,
                soft_critiques=blackboard.open_critiques,
            )

        blackboard.student_summary = summary
        summary_payload = summary.model_dump()
        summary_payload["reasoningTrace"] = build_explainer_trace(
            summary=summary_payload,
            transcript_roles=[
                str(turn.get("agent_role") or "")
                for turn in blackboard.transcript
                if turn.get("agent_role")
            ],
        )
        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=summary_payload,
            rationale="Generated student-facing summary from negotiation artifacts.",
            references=[f"explainer:source={summary.source}"],
        )
