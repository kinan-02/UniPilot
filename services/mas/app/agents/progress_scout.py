"""Progress Scout agent — soft degree-progress critiques."""

from __future__ import annotations

from app.orchestrator.artifacts import ProgressReport
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.reasoning_trace import build_progress_scout_trace
from app.services.variant_evaluation import build_progress_report


class ProgressScoutAgent:
    role = "progress_scout"

    @staticmethod
    def turn_from_evaluations(evaluations: list) -> AgentTurn:
        variants = [
            {
                "variant": evaluation.variant,
                "progressScore": evaluation.progress_report.progress_score,
                "unlockCount": evaluation.progress_report.unlock_count,
                "critiques": evaluation.progress_report.critiques,
            }
            for evaluation in evaluations
        ]
        has_critiques = any(item["critiques"] for item in variants)
        payload: dict = {"variants": variants}
        payload["reasoningTrace"] = build_progress_scout_trace(variants=variants)
        return AgentTurn(
            agent_role="progress_scout",
            action="critique",
            payload=payload,
            rationale=(
                "Soft progress pressure evaluated per planner variant."
                if has_critiques
                else "All variants advance degree progress in the active catalog graph."
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
                blackboard.progress_report = matching.progress_report
            return turn

        if blackboard.candidate_plan is None or blackboard.engine is None:
            report = ProgressReport(
                progress_score=0.0,
                critiques=[{"type": "missing_plan", "message": "No plan to review for progress."}],
            )
            blackboard.progress_report = report
            payload = report.model_dump()
            payload["reasoningTrace"] = build_progress_scout_trace(
                progress_score=report.progress_score,
                unlock_count=report.unlock_count,
                critiques=report.critiques,
            )
            return AgentTurn(
                agent_role=self.role,
                action="critique",
                payload=payload,
                rationale="No candidate plan available for progress review.",
                references=[],
            )

        report = build_progress_report(
            engine=blackboard.engine,
            proposal=blackboard.candidate_plan,
            completed_courses=blackboard.completed_courses,
            user_context=blackboard.user_context,
        )
        blackboard.progress_report = report

        payload = report.model_dump()
        payload["reasoningTrace"] = build_progress_scout_trace(
            progress_score=report.progress_score,
            unlock_count=report.unlock_count,
            critiques=report.critiques,
        )

        if report.critiques:
            return AgentTurn(
                agent_role=self.role,
                action="critique",
                payload=payload,
                rationale=(
                    "Soft progress pressure: plan is feasible but may not maximize "
                    "degree advancement."
                ),
                references=report.references,
            )

        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=payload,
            rationale="Plan advances degree progress in the active catalog graph.",
            references=report.references,
        )
