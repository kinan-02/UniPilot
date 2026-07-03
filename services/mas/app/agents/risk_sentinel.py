"""Risk Sentinel agent — hard safety checks (credit overload)."""

from __future__ import annotations

from app.orchestrator.artifacts import RiskReport, Violation, ViolationType
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.orchestrator.violations import violation_messages
from app.services.reasoning_trace import build_risk_trace
from app.services.plan_hard_constraints import evaluate_hard_constraints, hard_violation_messages


class RiskSentinelAgent:
    role = "risk_sentinel"

    @staticmethod
    def turn_from_report(report: RiskReport) -> AgentTurn:
        pressured = bool(report.evidence.get("probation", {}).get("pressured"))
        typed_violations = [item.model_dump() for item in report.violations]
        trace = build_risk_trace(
            approved=report.ok,
            violations=typed_violations,
            evidence=report.evidence,
            probation_pressured=pressured,
        )
        if not report.ok:
            return AgentTurn(
                agent_role="risk_sentinel",
                action="veto",
                payload={
                    "riskType": "credit_overload",
                    "evidence": report.evidence,
                    "violations": violation_messages(report.violations),
                    "probationPressured": pressured,
                    "reasoningTrace": trace,
                },
                rationale="Hard safety veto from deterministic workload analysis.",
                references=report.references,
            )

        rationale = "Planned workload is within the student's credit limit."
        if pressured:
            rationale += " Note: GPA is below probation threshold — consider a lighter load."

        return AgentTurn(
            agent_role="risk_sentinel",
            action="critique",
            payload={
                "approved": True,
                "evidence": report.evidence,
                "probationPressured": pressured,
                "reasoningTrace": trace,
            },
            rationale=rationale,
            references=report.references,
        )

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        proposal = blackboard.candidate_plan
        if proposal is None or blackboard.engine is None:
            typed = [
                Violation(
                    type=ViolationType.MISSING_PLAN,
                    message="No candidate plan to evaluate for workload risk.",
                )
            ]
            report = RiskReport(ok=False, violations=typed)
            blackboard.risk_report = report
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
        blackboard.risk_report = hard.risk
        turn = self.turn_from_report(hard.risk)

        if hard.feasibility.ok and not hard.risk.ok:
            blackboard.apply_veto(
                agent_role=self.role,
                violations=hard_violation_messages(hard),
                references=hard.references,
                typed_violations=hard.violations,
            )
        return turn
