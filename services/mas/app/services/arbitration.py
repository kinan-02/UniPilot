"""Arbitration helpers — score and choose among feasible candidate plans."""

from __future__ import annotations

from typing import Any

from app.orchestrator.artifacts import ArbitrationResult, VariantEvaluation
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.orchestrator.utility import score_variant_evaluation
from app.services.academic_risk_cache import get_cached_academic_risk
from app.services.plan_hard_constraints import evaluate_hard_constraints


def feasible_candidates(
    blackboard: Blackboard,
    proposals: list[PlanProposal],
) -> list[PlanProposal]:
    if blackboard.engine is None:
        return list(proposals)

    survivors: list[PlanProposal] = []
    for proposal in proposals:
        academic_risk_analysis = get_cached_academic_risk(blackboard, proposal.course_ids)
        hard = evaluate_hard_constraints(
            course_ids=proposal.course_ids,
            engine=blackboard.engine,
            completed_courses=blackboard.completed_courses,
            user_context=blackboard.user_context,
            academic_risk_analysis=academic_risk_analysis,
        )
        if hard.ok and proposal.course_ids:
            survivors.append(proposal)
    return survivors


def arbitrate_candidates(
    blackboard: Blackboard,
    proposals: list[PlanProposal],
    *,
    variant_evaluations: list[VariantEvaluation] | None = None,
) -> tuple[PlanProposal | None, ArbitrationResult]:
    if blackboard.engine is None:
        return None, ArbitrationResult()

    evaluation_by_variant = {
        evaluation.variant: evaluation for evaluation in (variant_evaluations or [])
    }
    feasible = feasible_candidates(blackboard, proposals)
    if not feasible and blackboard.best_seen_plan is not None:
        feasible = [blackboard.best_seen_plan]

    scored: list[tuple[PlanProposal, float, dict[str, Any]]] = []
    for proposal in feasible:
        evaluation = evaluation_by_variant.get(proposal.variant)
        if evaluation is not None:
            utility, breakdown = score_variant_evaluation(
                proposal=proposal,
                evaluation=evaluation,
                engine=blackboard.engine,
                user_context=blackboard.user_context,
                risk_report=blackboard.risk_report,
            )
        else:
            from app.orchestrator.utility import score_plan

            utility, breakdown = score_plan(
                proposal=proposal,
                engine=blackboard.engine,
                user_context=blackboard.user_context,
                soft_critiques=blackboard.open_critiques,
                risk_report=blackboard.risk_report,
            )
        scored.append((proposal, utility, breakdown))

    if not scored:
        return None, ArbitrationResult()

    scored.sort(key=lambda item: item[1], reverse=True)
    chosen, utility, breakdown = scored[0]
    rejected = [
        {
            "variant": proposal.variant,
            "course_ids": list(proposal.course_ids),
            "utility": round(candidate_utility, 4),
        }
        for proposal, candidate_utility, _candidate_breakdown in scored[1:]
    ]

    result = ArbitrationResult(
        chosen_variant=chosen.variant,
        utility=utility,
        breakdown=breakdown,
        considered_variants=[proposal.variant for proposal, _, _ in scored],
        rejected_alternatives=rejected,
    )
    return chosen, result
