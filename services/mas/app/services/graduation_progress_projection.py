"""Project graduation-progress baseline after a hypothetical semester plan."""

from __future__ import annotations

import copy
from typing import Any

from app.config import Settings, get_settings
from app.effectors.gateway import get_effector_gateway
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_progress import _normalize_course_number, _remaining_mandatory_numbers
from app.services.planner_support import parse_course_credits


async def resolve_projected_graduation_progress(
    *,
    user_context: dict[str, Any],
    course_ids: list[str],
    engine: AcademicGraphEngine,
    settings: Settings | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """
    Resolve projected graduation progress for a variant plan.

    Prefers API recompute when available; falls back to local shallow projection.
    """
    baseline = user_context.get("graduation_progress")
    if not isinstance(baseline, dict) or not course_ids:
        return baseline if isinstance(baseline, dict) else None, "baseline_only"

    user_id = str(user_context.get("user_id") or "")
    completed = user_context.get("completed_courses")
    completed_numbers = list(completed) if isinstance(completed, list) else None

    if user_id:
        preview = await get_effector_gateway().preview_graduation_progress(
            user_id=user_id,
            completed_course_numbers=completed_numbers,
            additional_course_numbers=list(course_ids),
            settings=settings or get_settings(),
        )
        if isinstance(preview, dict):
            return preview, "api_recompute"

    projected = project_graduation_progress_after_plan(
        baseline=baseline,
        course_ids=course_ids,
        engine=engine,
    )
    return projected, "local_projection"


def project_graduation_progress_after_plan(
    *,
    baseline: dict[str, Any],
    course_ids: list[str],
    engine: AcademicGraphEngine,
) -> dict[str, Any]:
    """Return a shallow-projected progress snapshot if the plan courses were completed."""
    if not baseline or not course_ids:
        return baseline

    projected = copy.deepcopy(baseline)
    planned_numbers = {_normalize_course_number(course_id) for course_id in course_ids}
    remaining_entries = list(baseline.get("remainingMandatoryCourses") or [])
    remaining_numbers = _remaining_mandatory_numbers(baseline)

    satisfied_numbers = planned_numbers.intersection(remaining_numbers)
    if satisfied_numbers:
        projected["remainingMandatoryCourses"] = [
            entry
            for entry in remaining_entries
            if _normalize_course_number(
                str(entry.get("courseNumber") or entry.get("number") or "")
            )
            not in satisfied_numbers
        ]

    plan_credits = sum(parse_course_credits(engine, course_id) for course_id in course_ids)
    completed_credits = float(baseline.get("completedCredits") or 0)
    total_required = float(baseline.get("totalRequiredCredits") or 0)
    credits_remaining = float(baseline.get("creditsRemaining") or 0)

    projected_completed = min(
        total_required if total_required > 0 else completed_credits + plan_credits,
        completed_credits + plan_credits,
    )
    projected_remaining = max(0.0, credits_remaining - plan_credits)

    projected["completedCredits"] = round(projected_completed, 2)
    projected["creditsRemaining"] = round(projected_remaining, 2)
    if total_required > 0:
        projected["completionPercentage"] = round(
            min(100.0, (projected_completed / total_required) * 100.0),
            2,
        )

    projected["projectionMeta"] = {
        "source": "mas_variant_projection",
        "plannedCourseIds": list(course_ids),
        "plannedCredits": round(plan_credits, 2),
        "mandatorySatisfied": sorted(satisfied_numbers),
    }
    return projected
