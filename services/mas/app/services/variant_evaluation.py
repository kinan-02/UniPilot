"""Per-variant soft critic evaluation for MAS arbitration."""

from __future__ import annotations

from typing import Any

from app.effectors.gateway import get_effector_gateway
from app.orchestrator.artifacts import PreferenceReport, ProgressReport, VariantEvaluation
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.academic_risk_cache import get_cached_academic_risk
from app.services.graduation_progress_projection import resolve_projected_graduation_progress
from app.services.plan_hard_constraints import evaluate_hard_constraints
from app.services.plan_progress import evaluate_degree_progress
from app.services.preference_support import evaluate_soft_preferences


def _build_trade_offs(critiques: list[dict]) -> list[dict]:
    trade_offs: list[dict] = []
    for critique in critiques:
        course_id = critique.get("courseId")
        if critique.get("type") == "day_preference_conflict" and course_id:
            trade_offs.append(
                {
                    "action": "drop",
                    "courseId": course_id,
                    "gains": ["Avoid preferred day-off conflicts"],
                    "message": critique.get("message"),
                }
            )
        elif critique.get("type") == "below_min_credits":
            trade_offs.append(
                {
                    "action": "add_course",
                    "gains": ["Reach preferred minimum credit load"],
                    "message": critique.get("message"),
                }
            )
    return trade_offs


def build_progress_report(
    *,
    engine: AcademicGraphEngine,
    proposal: PlanProposal,
    completed_courses: list[str],
    user_context: dict[str, Any],
    projected_graduation_progress: dict[str, Any] | None = None,
    projection_source: str | None = None,
) -> ProgressReport:
    baseline = user_context.get("graduation_progress")
    projected = projected_graduation_progress
    if projected is None and isinstance(baseline, dict) and proposal.course_ids:
        from app.services.graduation_progress_projection import project_graduation_progress_after_plan

        projected = project_graduation_progress_after_plan(
            baseline=baseline,
            course_ids=proposal.course_ids,
            engine=engine,
        )

    score, unlock_count, critiques, references = evaluate_degree_progress(
        engine=engine,
        course_ids=proposal.course_ids,
        completed_courses=completed_courses,
        user_context=user_context,
        graduation_progress=projected if isinstance(projected, dict) else baseline,
    )
    if projection_source:
        references.append(f"progress:projection_source={projection_source}")
    return ProgressReport(
        progress_score=score,
        unlock_count=unlock_count,
        critiques=critiques,
        references=references,
    )


def build_preference_report(
    *,
    engine: AcademicGraphEngine,
    proposal: PlanProposal,
    user_context: dict[str, Any],
) -> PreferenceReport:
    critiques, references = evaluate_soft_preferences(
        engine=engine,
        course_ids=proposal.course_ids,
        user_context=user_context,
    )
    return PreferenceReport(
        critiques=critiques,
        trade_offs=_build_trade_offs(critiques),
        references=references,
    )


def evaluate_variant(
    blackboard: Blackboard,
    proposal: PlanProposal,
    *,
    projected_graduation_progress: dict[str, Any] | None = None,
    projection_source: str | None = None,
) -> VariantEvaluation:
    """Evaluate soft critics and hard gate for one planner variant."""
    engine = blackboard.engine
    if engine is None:
        return VariantEvaluation(
            variant=proposal.variant,
            course_ids=list(proposal.course_ids),
            hard_ok=False,
        )

    academic_risk_analysis = get_cached_academic_risk(blackboard, proposal.course_ids)
    hard = evaluate_hard_constraints(
        course_ids=proposal.course_ids,
        engine=engine,
        completed_courses=blackboard.completed_courses,
        user_context=blackboard.user_context,
        academic_risk_analysis=academic_risk_analysis,
    )
    progress_report = build_progress_report(
        engine=engine,
        proposal=proposal,
        completed_courses=blackboard.completed_courses,
        user_context=blackboard.user_context,
        projected_graduation_progress=projected_graduation_progress,
        projection_source=projection_source,
    )
    preference_report = build_preference_report(
        engine=engine,
        proposal=proposal,
        user_context=blackboard.user_context,
    )

    return VariantEvaluation(
        variant=proposal.variant,
        course_ids=list(proposal.course_ids),
        progress_report=progress_report,
        preference_report=preference_report,
        hard_ok=hard.ok,
    )


async def evaluate_all_variants(
    blackboard: Blackboard,
    proposals: list[PlanProposal],
) -> list[VariantEvaluation]:
    await get_effector_gateway().preload_academic_risk_cache(blackboard, proposals)

    if blackboard.engine is None:
        return [evaluate_variant(blackboard, proposal) for proposal in proposals]

    projections: list[tuple[dict[str, Any] | None, str | None]] = []
    for proposal in proposals:
        projected, source = await resolve_projected_graduation_progress(
            user_context=blackboard.user_context,
            course_ids=proposal.course_ids,
            engine=blackboard.engine,  # type: ignore[arg-type]
            settings=blackboard.settings,
        )
        projections.append((projected, source))

    return [
        evaluate_variant(
            blackboard,
            proposal,
            projected_graduation_progress=projected,
            projection_source=source,
        )
        for proposal, (projected, source) in zip(proposals, projections, strict=True)
    ]
