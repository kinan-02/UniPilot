"""Red-team agent — post-commit devil's advocate review (read-only)."""

from __future__ import annotations

from typing import Any

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn, PlanProposal
from app.services.plan_risk import resolve_max_credits
from app.services.planner_support import sum_plan_credits
from app.services.reasoning_trace import build_red_team_trace


class RedTeamAgent:
    role = "red_team"

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        proposal = blackboard.candidate_plan or PlanProposal()
        attacks = self._collect_attacks(blackboard, proposal)
        severity = self._overall_severity(attacks)
        payload: dict[str, Any] = {
            "attacks": attacks,
            "severity": severity,
            "attackCount": len(attacks),
            "reasoningTrace": build_red_team_trace(
                attacks=attacks,
                severity=severity,
                chosen_variant=proposal.variant,
            ),
        }
        rationale = (
            f"Red-team identified {len(attacks)} concern(s) with severity {severity}."
            if attacks
            else "Red-team found no material concerns with the committed plan."
        )
        references = [f"red_team:severity={severity}", f"red_team:attacks={len(attacks)}"]
        return AgentTurn(
            agent_role=self.role,
            action="critique",
            payload=payload,
            rationale=rationale,
            references=references,
        )

    def _collect_attacks(
        self,
        blackboard: Blackboard,
        proposal: PlanProposal,
    ) -> list[dict[str, Any]]:
        attacks: list[dict[str, Any]] = []
        engine = blackboard.engine

        for critique in list(blackboard.open_critiques or [])[:4]:
            message = str(critique.get("message") or critique.get("type") or "").strip()
            if message:
                attacks.append(
                    {
                        "type": "unresolved_preference",
                        "severity": "medium",
                        "message": message,
                    }
                )

        if engine is not None and proposal.course_ids:
            max_credits = resolve_max_credits(blackboard.user_context)
            total_credits = sum_plan_credits(engine, proposal.course_ids)
            if max_credits > 0 and total_credits >= max_credits * 0.95:
                attacks.append(
                    {
                        "type": "high_credit_load",
                        "severity": "medium",
                        "message": (
                            f"Plan uses {total_credits:.1f}/{max_credits:.1f} credits — "
                            "little headroom if a course becomes unavailable."
                        ),
                    }
                )

        risk_report = blackboard.risk_report
        if risk_report is not None:
            probation = risk_report.evidence.get("probation") or {}
            if isinstance(probation, dict) and probation.get("pressured"):
                attacks.append(
                    {
                        "type": "probation_pressure",
                        "severity": "high",
                        "message": (
                            "Academic risk preview shows probation pressure with this workload."
                        ),
                    }
                )

        arbitration = blackboard.arbitration
        if arbitration is not None and arbitration.rejected_alternatives:
            best_rejected = max(
                arbitration.rejected_alternatives,
                key=lambda item: float(item.get("utility") or 0),
            )
            if float(best_rejected.get("utility") or 0) >= arbitration.utility * 0.95:
                attacks.append(
                    {
                        "type": "close_alternative",
                        "severity": "low",
                        "message": (
                            f"Variant '{best_rejected.get('variant')}' scored nearly as high "
                            f"({best_rejected.get('utility')}) — student may prefer its trade-offs."
                        ),
                    }
                )

        if len(proposal.course_ids) == 1:
            attacks.append(
                {
                    "type": "thin_plan",
                    "severity": "low",
                    "message": (
                        "Single-course plan may under-use the semester unless the student "
                        "intentionally wants a light load."
                    ),
                }
            )

        return attacks

    @staticmethod
    def _overall_severity(attacks: list[dict[str, Any]]) -> str:
        if any(attack.get("severity") == "high" for attack in attacks):
            return "high"
        if any(attack.get("severity") == "medium" for attack in attacks):
            return "medium"
        if attacks:
            return "low"
        return "none"
