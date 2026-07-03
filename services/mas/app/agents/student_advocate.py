"""Student Advocate agent — soft preference critiques (no veto authority)."""

from __future__ import annotations

from app.orchestrator.artifacts import PreferenceReport
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.reasoning_trace import build_advocate_trace
from app.services.variant_evaluation import build_preference_report


class StudentAdvocateAgent:
    role = "student_advocate"

    @staticmethod
    def turn_from_evaluations(evaluations: list) -> AgentTurn:
        """Summarize per-variant preference reports for the transcript."""
        variants = [
            {
                "variant": evaluation.variant,
                "critiques": evaluation.preference_report.critiques,
                "tradeOffs": evaluation.preference_report.trade_offs,
            }
            for evaluation in evaluations
        ]
        total_critiques = sum(len(item["critiques"]) for item in variants)
        payload: dict = {"variants": variants, "critiqueCount": total_critiques}
        payload["reasoningTrace"] = build_advocate_trace(
            critique_count=total_critiques,
            variants=variants,
        )
        return AgentTurn(
            agent_role="student_advocate",
            action="critique",
            payload=payload,
            rationale=(
                "Soft preference pressure evaluated per planner variant."
                if total_critiques
                else "All variants align with stated student preferences."
            ),
            references=[],
        )

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        if blackboard.variant_evaluations:
            turn = self.turn_from_evaluations(blackboard.variant_evaluations)
            if blackboard.candidate_plan is not None:
                matching = next(
                    (
                        evaluation
                        for evaluation in blackboard.variant_evaluations
                        if evaluation.variant == blackboard.candidate_plan.variant
                    ),
                    blackboard.variant_evaluations[0],
                )
                blackboard.preference_report = matching.preference_report
                blackboard.open_critiques = list(matching.preference_report.critiques)
            return turn

        if blackboard.candidate_plan is None or blackboard.engine is None:
            report = PreferenceReport(
                critiques=[{"type": "missing_plan", "message": "No plan to review."}]
            )
            blackboard.preference_report = report
            payload = report.model_dump()
            payload["reasoningTrace"] = build_advocate_trace(
                critiques=report.critiques,
                trade_offs=report.trade_offs,
            )
            return AgentTurn(
                agent_role=self.role,
                action="critique",
                payload=payload,
                rationale="No candidate plan available for preference review.",
                references=[],
            )

        report = build_preference_report(
            engine=blackboard.engine,
            proposal=blackboard.candidate_plan,
            user_context=blackboard.user_context,
        )
        blackboard.preference_report = report
        blackboard.open_critiques = list(report.critiques)

        payload = report.model_dump()
        payload["reasoningTrace"] = build_advocate_trace(
            critiques=report.critiques,
            trade_offs=report.trade_offs,
            critique_count=len(report.critiques),
        )

        if report.critiques:
            return AgentTurn(
                agent_role=self.role,
                action="critique",
                payload=payload,
                rationale=(
                    "Soft preference pressure: plan is feasible but does not fully match "
                    "student constraints."
                ),
                references=report.references,
            )

        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=payload,
            rationale="Plan aligns with stated student preferences.",
            references=report.references,
        )
