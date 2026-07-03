"""Policy responder agent — regulations Q&A without semester planning."""

from __future__ import annotations

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.policy_qa import build_policy_answer


class PolicyResponderAgent:
    role = "policy_responder"

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        engine = blackboard.engine
        if engine is None:
            return AgentTurn(
                agent_role=self.role,
                action="critique",
                payload={"answer": "Policy Q&A requires an active academic knowledge graph."},
                rationale="No catalog engine available for regulations search.",
                references=[],
            )

        answer, citations = build_policy_answer(engine, question=blackboard.goal)
        payload = {
            "answer": answer,
            "citations": citations,
            "vertical": "policy_qa",
            "citationCount": len(citations),
        }
        references = [str(item.get("reference") or "") for item in citations if item.get("reference")]
        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=payload,
            rationale=f"Retrieved {len(citations)} regulation citation(s) from the wiki corpus.",
            references=references,
        )
