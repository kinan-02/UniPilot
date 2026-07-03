"""Finalize phase — variant eval, soft critics, arbiter, explain, red-team, validate."""

from __future__ import annotations

import asyncio

from app.agents.registry import AgentRegistry
from app.effectors.gateway import get_effector_gateway
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import NegotiationResult
from app.orchestrator.utility import score_plan, score_variant_evaluation
from app.services.arbitration import feasible_candidates
from app.services.counterfactual_explanations import build_counterfactual_explanations
from app.services.path_relevant_planner import build_path_context_summary
from app.services.variant_evaluation import evaluate_all_variants
from app.orchestrator.workflow.snapshot import workflow_snapshot
from app.orchestrator.workflow.validate import validate_committed_plan


async def prepare_variant_evaluations(blackboard: Blackboard) -> None:
    proposals = list(blackboard.candidate_plans)
    if not proposals and blackboard.candidate_plan is not None:
        proposals = [blackboard.candidate_plan]

    await get_effector_gateway().preload_academic_risk_cache(blackboard, proposals)
    feasible = feasible_candidates(blackboard, proposals)
    evaluation_targets = feasible if feasible else proposals
    blackboard.variant_evaluations = await evaluate_all_variants(blackboard, evaluation_targets)


async def run_soft_advocates(blackboard: Blackboard, agents: AgentRegistry) -> None:
    progress_turn, advocate_turn = await asyncio.gather(
        agents.progress_scout.run(blackboard),
        agents.student_advocate.run(blackboard),
    )
    blackboard.record_turn(progress_turn)
    blackboard.record_turn(advocate_turn)


def record_best_candidate(blackboard: Blackboard) -> None:
    if blackboard.candidate_plan is None or blackboard.engine is None:
        return
    matching_evaluation = next(
        (
            evaluation
            for evaluation in blackboard.variant_evaluations
            if evaluation.variant == blackboard.candidate_plan.variant
        ),
        None,
    )
    if matching_evaluation is not None:
        utility, breakdown = score_variant_evaluation(
            proposal=blackboard.candidate_plan,
            evaluation=matching_evaluation,
            engine=blackboard.engine,
            user_context=blackboard.user_context,
            risk_report=blackboard.risk_report,
        )
    else:
        utility, breakdown = score_plan(
            proposal=blackboard.candidate_plan,
            engine=blackboard.engine,
            user_context=blackboard.user_context,
            soft_critiques=blackboard.open_critiques,
            risk_report=blackboard.risk_report,
        )
    if utility >= blackboard.best_seen_score:
        blackboard.best_seen_score = utility
        blackboard.best_seen_plan = blackboard.candidate_plan
        blackboard.utility_breakdown = breakdown


def relax_soft_constraints(blackboard: Blackboard) -> bool:
    """Relax negotiable preferences when hard feasibility blocks progress."""
    constraints = dict(blackboard.user_context.get("constraints") or {})
    relaxed_any = False
    if constraints.pop("avoidDays", None) is not None:
        blackboard.record_relaxation("Relaxed avoidDays preference to unblock negotiation.")
        relaxed_any = True
    if constraints.pop("preferredDaysOff", None) is not None:
        blackboard.record_relaxation("Relaxed preferredDaysOff preference to unblock negotiation.")
        relaxed_any = True
    if constraints.pop("minCredits", None) is not None:
        blackboard.record_relaxation("Relaxed minCredits preference to unblock negotiation.")
        relaxed_any = True
    if relaxed_any:
        blackboard.user_context = {**blackboard.user_context, "constraints": constraints}
    return relaxed_any


def _enrich_final_decision(
    blackboard: Blackboard,
    *,
    arbiter_payload: dict,
    red_team_payload: dict,
) -> dict:
    final_decision = dict(arbiter_payload)
    if blackboard.student_summary is not None:
        final_decision["studentSummary"] = blackboard.student_summary.model_dump()
    if blackboard.variant_evaluations:
        final_decision["variantEvaluations"] = [
            evaluation.model_dump() for evaluation in blackboard.variant_evaluations
        ]
    arbitration_payload = final_decision.get("arbitration")
    if isinstance(arbitration_payload, dict):
        chosen_utility = None
        breakdown = final_decision.get("utilityBreakdown")
        if isinstance(breakdown, dict):
            chosen_utility = breakdown.get("utility")
        final_decision["counterfactualExplanations"] = build_counterfactual_explanations(
            chosen_variant=str(
                final_decision.get("variant") or arbitration_payload.get("chosen_variant") or ""
            ),
            chosen_utility=float(chosen_utility) if isinstance(chosen_utility, (int, float)) else None,
            arbitration=arbitration_payload,
            variant_evaluations=final_decision.get("variantEvaluations") or [],
        )
    final_decision["redTeamReview"] = red_team_payload
    path_context = build_path_context_summary(blackboard.user_context)
    data_quality = path_context.get("dataQuality")
    has_warnings = (
        isinstance(data_quality, dict)
        and isinstance(data_quality.get("warnings"), list)
        and len(data_quality["warnings"]) > 0
    )
    if (
        path_context.get("priorityRemainingCourses")
        or path_context.get("trackSlug")
        or path_context.get("planSemesterCode")
        or path_context.get("planningSource")
        or (path_context.get("completedCourseCount") or 0) > 0
        or has_warnings
    ):
        final_decision["pathContext"] = path_context
    what_if = blackboard.user_context.get("what_if")
    if isinstance(what_if, dict):
        final_decision["whatIf"] = what_if
        baseline = blackboard.user_context.get("what_if_baseline")
        if isinstance(baseline, dict):
            final_decision["whatIfComparison"] = {
                "baselineCompletedCourses": list(baseline.get("completed_courses") or []),
                "scenarioCompletedCourses": list(blackboard.completed_courses),
                "baselineTrackSlug": baseline.get("track_slug"),
                "scenarioTrackSlug": blackboard.user_context.get("track_slug"),
            }
    return final_decision


async def finalize_success(
    blackboard: Blackboard,
    agents: AgentRegistry,
) -> NegotiationResult:
    """Run post-plan phases and validate before returning a completed result."""
    await prepare_variant_evaluations(blackboard)
    await workflow_snapshot(blackboard, "variant_evaluations")
    await run_soft_advocates(blackboard, agents)
    await workflow_snapshot(blackboard, "soft_advocates")

    arbiter_turn = await agents.arbiter.commit(blackboard)
    blackboard.record_turn(arbiter_turn)
    await workflow_snapshot(blackboard, "arbiter")

    course_ids = list(arbiter_turn.payload.get("course_ids") or [])
    ok, violations, validation_refs = validate_committed_plan(
        blackboard=blackboard,
        course_ids=course_ids,
    )
    if not ok:
        return NegotiationResult(
            status="failed",
            transcript=blackboard.transcript,
            rounds=blackboard.unique_agent_roles(),
            error="Pre-commit validation failed: " + "; ".join(violations[:4]),
        )

    explainer_turn = await agents.explainer.run(blackboard)
    blackboard.record_turn(explainer_turn)
    await workflow_snapshot(blackboard, "explainer")

    red_team_turn = await agents.red_team.run(blackboard)
    blackboard.record_turn(red_team_turn)
    await workflow_snapshot(blackboard, "red_team")

    final_decision = _enrich_final_decision(
        blackboard,
        arbiter_payload=arbiter_turn.payload,
        red_team_payload=red_team_turn.payload,
    )
    final_decision["validationReferences"] = validation_refs

    return NegotiationResult(
        status="completed",
        final_decision=final_decision,
        utility_breakdown=blackboard.utility_breakdown,
        transcript=blackboard.transcript,
        rounds=blackboard.unique_agent_roles(),
    )
