"""Build multiple planner candidate variants for Arbiter arbitration."""

from __future__ import annotations

from typing import Any

from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import (
    filter_eligible_courses,
    list_eligible_catalog_courses,
    parse_course_credits,
    sum_plan_credits,
)
from app.services.plan_risk import resolve_max_credits


def _clone_variant(proposal: PlanProposal, *, variant: str, notes: str) -> PlanProposal:
    return PlanProposal(
        course_ids=list(proposal.course_ids),
        semester_filename=proposal.semester_filename,
        notes=notes,
        variant=variant,
    )


def build_candidate_variants(
    primary: PlanProposal,
    *,
    engine: AcademicGraphEngine,
    user_context: dict[str, Any],
    completed_courses: list[str],
    technion_raw_dir: str,
) -> list[PlanProposal]:
    """
    Layer 3 — deterministic multi-candidate expansion.

    Produces up to three variants: primary, alternate_safe, alternate_progress.
    """
    if not primary.course_ids:
        return [_clone_variant(primary, variant="primary", notes=primary.notes)]

    variants: list[PlanProposal] = [
        _clone_variant(primary, variant="primary", notes=primary.notes or "Primary planner proposal."),
    ]

    max_credits = resolve_max_credits(user_context)

    if len(primary.course_ids) > 1:
        safe_ids = list(primary.course_ids)
        while len(safe_ids) > 1 and sum_plan_credits(engine, safe_ids) > max_credits * 0.75:
            drop_id = max(safe_ids, key=lambda course_id: parse_course_credits(engine, course_id))
            safe_ids = [course_id for course_id in safe_ids if course_id != drop_id]
        if safe_ids != primary.course_ids:
            variants.append(
                _clone_variant(
                    PlanProposal(
                        course_ids=safe_ids,
                        semester_filename=primary.semester_filename,
                    ),
                    variant="alternate_safe",
                    notes="Safer alternate with reduced credit load.",
                )
            )

    catalog = list_eligible_catalog_courses(
        engine,
        completed_courses,
        user_context=user_context,
    )
    existing = set(primary.course_ids)
    running_credits = sum_plan_credits(engine, primary.course_ids)
    progress_ids = list(primary.course_ids)

    for course_id in catalog:
        if course_id in existing:
            continue
        credits = parse_course_credits(engine, course_id)
        if running_credits + credits > max_credits:
            continue
        progress_ids.append(course_id)
        running_credits += credits
        break

    if progress_ids != primary.course_ids:
        verified, _refs = filter_eligible_courses(
            engine=engine,
            technion_raw_dir=technion_raw_dir,
            course_ids=progress_ids,
            completed_courses=completed_courses,
            semester_filename=primary.semester_filename,
        )
        if verified and verified != primary.course_ids:
            variants.append(
                _clone_variant(
                    PlanProposal(
                        course_ids=verified,
                        semester_filename=primary.semester_filename,
                    ),
                    variant="alternate_progress",
                    notes="Progress-oriented alternate with an extra eligible course when possible.",
                )
            )

    # Deduplicate by course set while preserving first variant label
    seen: set[tuple[str, ...]] = set()
    unique: list[PlanProposal] = []
    for variant in variants:
        key = tuple(variant.course_ids)
        if key in seen:
            continue
        seen.add(key)
        unique.append(variant)
    return unique
