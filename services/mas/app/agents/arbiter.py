"""Arbiter agent — utility scoring and final commit."""

from __future__ import annotations

from typing import Any

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.arbitration import arbitrate_candidates
from app.services.plan_schedule import build_plan_schedule_summary
from app.services.reasoning_trace import build_arbitration_trace


class ArbiterAgent:
    role = "arbiter"

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        return await self.commit(blackboard)

    async def commit(self, blackboard: Blackboard) -> AgentTurn:
        proposals = list(blackboard.candidate_plans)
        if not proposals and blackboard.candidate_plan is not None:
            proposals = [blackboard.candidate_plan]

        chosen, arbitration = arbitrate_candidates(
            blackboard,
            proposals,
            variant_evaluations=blackboard.variant_evaluations,
        )
        if chosen is None or blackboard.engine is None:
            raise RuntimeError("Arbiter cannot commit without a feasible candidate plan")

        blackboard.set_candidate(chosen)
        blackboard.arbitration = arbitration
        blackboard.utility_breakdown = arbitration.breakdown

        matching = next(
            (
                evaluation
                for evaluation in blackboard.variant_evaluations
                if evaluation.variant == chosen.variant
            ),
            None,
        )
        if matching is not None:
            blackboard.progress_report = matching.progress_report
            blackboard.preference_report = matching.preference_report
            blackboard.open_critiques = list(matching.preference_report.critiques)

        if arbitration.utility >= blackboard.best_seen_score:
            blackboard.best_seen_score = arbitration.utility
            blackboard.best_seen_plan = chosen

        schedule_summary = build_plan_schedule_summary(
            engine=blackboard.engine,
            course_ids=list(chosen.course_ids),
            semester_filename=chosen.semester_filename,
        )

        final_decision: dict[str, Any] = {
            "type": "next_semester_plan",
            "course_ids": list(chosen.course_ids),
            "variant": chosen.variant,
            "semester_filename": chosen.semester_filename,
            "planSemesterCode": schedule_summary.get("planSemesterCode"),
            "semesterLabel": schedule_summary.get("semesterLabel"),
            "totalCredits": schedule_summary.get("totalCredits"),
            "schedule": schedule_summary,
            "completed_courses_considered": blackboard.completed_courses,
            "utilityBreakdown": arbitration.breakdown,
            "arbitration": arbitration.model_dump(),
            "goalSpec": blackboard.goal_spec.model_dump() if blackboard.goal_spec else None,
            "softCritiques": list(blackboard.open_critiques),
            "relaxedConstraints": list(blackboard.relaxed_constraints),
            "reasoningTrace": build_arbitration_trace(arbitration=arbitration.model_dump()),
        }

        return AgentTurn(
            agent_role=self.role,
            action="commit",
            payload=final_decision,
            rationale=(
                "Utility arbitration: commit validated plan variant "
                f"{chosen.variant} with score {arbitration.utility:.4f}."
            ),
            references=list(blackboard.validation_references),
        )
