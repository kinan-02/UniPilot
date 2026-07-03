"""Unified catalog + workload hard constraint gate."""

from __future__ import annotations

from app.agents.catalog_scout import CatalogScoutAgent
from app.agents.risk_sentinel import RiskSentinelAgent
from app.effectors.gateway import get_effector_gateway
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn
from app.services.plan_hard_constraints import hard_violation_messages


async def run_hard_constraint_gate(blackboard: Blackboard) -> AgentTurn | None:
    """Evaluate hard constraints and record scout/sentinel transcript turns."""
    gateway = get_effector_gateway()
    proposal = blackboard.candidate_plan
    if proposal is None or blackboard.engine is None:
        scout_turn = await CatalogScoutAgent().run(blackboard)
        blackboard.record_turn(scout_turn)
        return scout_turn

    academic_risk_analysis = await gateway.fetch_academic_risk_preview(
        blackboard=blackboard,
        course_ids=proposal.course_ids,
    )
    hard = gateway.evaluate_hard_constraints(
        course_ids=proposal.course_ids,
        engine=blackboard.engine,
        completed_courses=blackboard.completed_courses,
        user_context=blackboard.user_context,
        academic_risk_analysis=academic_risk_analysis,
    )
    blackboard.feasibility_report = hard.feasibility
    blackboard.risk_report = hard.risk

    scout_turn = CatalogScoutAgent.turn_from_report(hard.feasibility)
    sentinel_turn = RiskSentinelAgent.turn_from_report(hard.risk)
    blackboard.record_turn(scout_turn)
    blackboard.record_turn(sentinel_turn)

    if not hard.ok:
        blackboard.apply_veto(
            agent_role=hard.veto_agent or "catalog_scout",
            violations=hard_violation_messages(hard),
            references=hard.references,
            typed_violations=hard.violations,
        )
        return scout_turn if not hard.feasibility.ok else sentinel_turn

    blackboard.apply_approval(references=hard.references)
    return None
