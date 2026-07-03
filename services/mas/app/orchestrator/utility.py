"""Utility scoring for Arbiter arbitration."""

from __future__ import annotations

from typing import Any

from app.orchestrator.artifacts import ProgressReport, RiskReport, VariantEvaluation
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_risk import resolve_max_credits
from app.services.planner_support import sum_plan_credits
from app.services.preference_support import preference_match_score

WEIGHTS = {
    "progress_gain": 0.18,
    "path_alignment": 0.28,
    "prereq_safety": 0.22,
    "load_balance": 0.18,
    "preference_match": 0.08,
    "risk_penalty": 0.10,
}

UTILITY_PROFILES: dict[str, dict[str, float]] = {
    "balanced": dict(WEIGHTS),
    "risk_averse": {
        "progress_gain": 0.18,
        "path_alignment": 0.17,
        "prereq_safety": 0.27,
        "load_balance": 0.28,
        "preference_match": 0.08,
        "risk_penalty": 0.20,
    },
    "aggressive": {
        "progress_gain": 0.28,
        "path_alignment": 0.22,
        "prereq_safety": 0.22,
        "load_balance": 0.13,
        "preference_match": 0.08,
        "risk_penalty": 0.05,
    },
}


def resolve_utility_weights(user_context: dict[str, Any]) -> dict[str, float]:
    constraints = user_context.get("constraints") or {}
    profile = str(constraints.get("utilityProfile") or "balanced").strip().lower()
    weights = UTILITY_PROFILES.get(profile)
    if weights is None:
        return dict(WEIGHTS)
    return dict(weights)


def _prereq_safety_score(
    engine: AcademicGraphEngine,
    course_ids: list[str],
    completed_courses: list[str],
) -> float:
    if not course_ids:
        return 0.0
    eligible_count = 0
    for course_id in course_ids:
        eligible, _missing = engine.evaluate_eligibility(course_id, completed_courses)
        if eligible:
            eligible_count += 1
    return eligible_count / len(course_ids)


def _load_balance_score(total_credits: float, max_credits: float) -> float:
    if max_credits <= 0:
        return 0.0
    if total_credits > max_credits:
        return 0.0
    utilization = total_credits / max_credits
    if utilization <= 0:
        return 0.2
    if utilization > 1.0:
        return 0.0
    return min(1.0, utilization)


def _progress_gain_score(
    course_ids: list[str],
    progress_report: ProgressReport | None = None,
) -> float:
    if progress_report is not None:
        return max(0.0, min(1.0, progress_report.progress_score))
    if not course_ids:
        return 0.0
    return min(1.0, len(course_ids) / 5.0)


def _preference_match_score(
    user_context: dict[str, Any],
    course_ids: list[str],
    soft_critiques: list[dict[str, Any]] | None = None,
) -> float:
    if not course_ids:
        return 0.0
    if soft_critiques is not None:
        return preference_match_score(soft_critiques, len(course_ids))
    if user_context.get("track_slug"):
        return 0.7
    return 0.5


def _risk_penalty_score(
    total_credits: float,
    max_credits: float,
    risk_report: RiskReport | None = None,
) -> float:
    penalty = 0.0
    if max_credits <= 0:
        penalty = 1.0
    elif total_credits > max_credits:
        overload_ratio = (total_credits - max_credits) / max_credits
        penalty = min(1.0, 0.5 + overload_ratio)
    elif total_credits <= max_credits:
        headroom = max_credits - total_credits
        penalty = max(0.0, 1.0 - headroom / max_credits)

    if risk_report and risk_report.evidence.get("probation", {}).get("pressured"):
        penalty = min(1.0, penalty + 0.15)
    return penalty


def _path_alignment_score(
    course_ids: list[str],
    user_context: dict[str, Any],
) -> float:
    priority = user_context.get("path_priority_courses")
    if not priority and not user_context.get("graduation_progress"):
        return 0.5
    from app.services.path_relevant_planner import score_plan_path_relevance

    score, _hits, _refs = score_plan_path_relevance(course_ids, user_context)
    return score


def score_plan(
    *,
    proposal: PlanProposal,
    engine: AcademicGraphEngine,
    user_context: dict[str, Any],
    soft_critiques: list[dict[str, Any]] | None = None,
    progress_report: ProgressReport | None = None,
    risk_report: RiskReport | None = None,
) -> tuple[float, dict[str, Any]]:
    course_ids = list(proposal.course_ids)
    completed = list(user_context.get("completed_courses") or [])
    max_credits = resolve_max_credits(user_context)
    total_credits = sum_plan_credits(engine, course_ids)

    components = {
        "progress_gain": _progress_gain_score(course_ids, progress_report),
        "path_alignment": _path_alignment_score(course_ids, user_context),
        "prereq_safety": _prereq_safety_score(engine, course_ids, completed),
        "load_balance": _load_balance_score(total_credits, max_credits),
        "preference_match": _preference_match_score(
            user_context,
            course_ids,
            soft_critiques=soft_critiques,
        ),
        "risk_penalty": _risk_penalty_score(total_credits, max_credits, risk_report),
    }

    weights = resolve_utility_weights(user_context)
    if not user_context.get("path_priority_courses") and not user_context.get("graduation_progress"):
        path_weight = weights.pop("path_alignment", 0.0)
        if path_weight > 0:
            weights["progress_gain"] = weights.get("progress_gain", 0.0) + path_weight * 0.6
            weights["prereq_safety"] = weights.get("prereq_safety", 0.0) + path_weight * 0.4

    utility = (
        weights.get("progress_gain", 0.0) * components["progress_gain"]
        + weights.get("path_alignment", 0.0) * components["path_alignment"]
        + weights.get("prereq_safety", 0.0) * components["prereq_safety"]
        + weights.get("load_balance", 0.0) * components["load_balance"]
        + weights.get("preference_match", 0.0) * components["preference_match"]
        - weights.get("risk_penalty", 0.0) * components["risk_penalty"]
    )

    breakdown = {
        "utility": round(utility, 4),
        "weights": weights,
        "utilityProfile": str((user_context.get("constraints") or {}).get("utilityProfile") or "balanced"),
        "components": {key: round(value, 4) for key, value in components.items()},
        "totalCredits": total_credits,
        "maxCredits": max_credits,
        "courseCount": len(course_ids),
        "softCritiqueCount": len(soft_critiques or []),
        "variant": proposal.variant,
    }
    return utility, breakdown


def score_variant_evaluation(
    *,
    proposal: PlanProposal,
    evaluation: VariantEvaluation,
    engine: AcademicGraphEngine,
    user_context: dict[str, Any],
    risk_report: RiskReport | None = None,
) -> tuple[float, dict[str, Any]]:
    return score_plan(
        proposal=proposal,
        engine=engine,
        user_context=user_context,
        soft_critiques=evaluation.preference_report.critiques,
        progress_report=evaluation.progress_report,
        risk_report=risk_report,
    )
