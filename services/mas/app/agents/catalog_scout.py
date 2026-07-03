"""Catalog Scout agent — hard feasibility checks against graph ground truth."""

from __future__ import annotations

from app.orchestrator.artifacts import FeasibilityReport, Violation, ViolationType
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.orchestrator.violations import violation_messages
from app.services.reasoning_trace import build_feasibility_trace
from app.services.plan_hard_constraints import evaluate_hard_constraints, hard_violation_messages


class CatalogScoutAgent:
    role = "catalog_scout"

    @staticmethod
    def turn_from_report(report: FeasibilityReport) -> AgentTurn:
        typed_violations = [item.model_dump() for item in report.violations]
        trace = build_feasibility_trace(approved=report.ok, violations=typed_violations)
        if not report.ok:
            return AgentTurn(
                agent_role="catalog_scout",
                action="veto",
                payload={
                    "violations": violation_messages(report.violations),
                    "typedViolations": typed_violations,
                    "reasoningTrace": trace,
                },
                rationale="Hard feasibility veto from graph ground truth.",
                references=report.references,
            )
        return AgentTurn(
            agent_role="catalog_scout",
            action="critique",
            payload={"approved": True, "typedViolations": [], "reasoningTrace": trace},
            rationale="All proposed courses are offered this semester and meet prerequisites.",
            references=report.references,
        )

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        proposal = blackboard.candidate_plan
        if proposal is None or blackboard.engine is None:
            typed = [
                Violation(
                    type=ViolationType.MISSING_PLAN,
                    message="No candidate plan to validate.",
                )
            ]
            report = FeasibilityReport(ok=False, violations=typed)
            blackboard.feasibility_report = report
            blackboard.apply_veto(
                agent_role=self.role,
                violations=violation_messages(typed),
                references=[],
                typed_violations=typed,
            )
            return self.turn_from_report(report)

        hard = evaluate_hard_constraints(
            course_ids=proposal.course_ids,
            engine=blackboard.engine,
            completed_courses=blackboard.completed_courses,
            user_context=blackboard.user_context,
        )
        blackboard.feasibility_report = hard.feasibility
        turn = self.turn_from_report(hard.feasibility)

        if not hard.feasibility.ok:
            blackboard.apply_veto(
                agent_role=self.role,
                violations=hard_violation_messages(hard),
                references=hard.references,
                typed_violations=hard.violations,
            )
        return turn
