"""LLM multi-strategy planner variant synthesis (safe / balanced / progress)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.llm.structured_output import invoke_structured_model
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import filter_eligible_courses, parse_course_credits
from app.services.plan_risk import resolve_max_credits


class _VariantPayload(BaseModel):
    primary: list[str] = Field(default_factory=list)
    alternate_safe: list[str] = Field(default_factory=list)
    alternate_progress: list[str] = Field(default_factory=list)
    notes: str = ""


def _normalize_course_ids(course_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(str(course_id).strip() for course_id in course_ids if course_id))


async def synthesize_planner_variants_with_llm(
    *,
    goal: str,
    primary: PlanProposal,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    completed_courses: list[str],
    user_context: dict[str, Any],
    settings: Settings | None = None,
) -> list[PlanProposal] | None:
    """
    Layer 2 — ask the LLM for three strategy variants, then verify eligibility.

    Returns None when LLM is unavailable or synthesis fails.
    """
    cfg = settings or get_settings()
    if not cfg.llm_configured() or not primary.course_ids:
        return None

    max_credits = resolve_max_credits(user_context)
    eligible_preview = ", ".join(primary.course_ids[:12])

    try:
        payload = await invoke_structured_model(
            system_prompt=(
                "You are the UniPilot Planner variant synthesizer. Given a primary semester "
                "course plan, propose three variants using only course IDs from the primary "
                "set or closely related eligible additions:\n"
                "- primary: keep the main proposal (may trim slightly)\n"
                "- alternate_safe: lighter credit load (roughly 70-85% of max credits)\n"
                "- alternate_progress: same or +1 course when credits allow\n"
                "Never invent course IDs. Respect max credits."
            ),
            user_prompt=(
                f"Goal: {goal}\n"
                f"Max credits: {max_credits}\n"
                f"Primary courses: {eligible_preview}\n"
                f"Completed courses: {', '.join(completed_courses[:20])}\n"
                "Return JSON: "
                '{"primary":["..."], "alternate_safe":["..."], '
                '"alternate_progress":["..."], "notes":"..."}'
            ),
            model_type=_VariantPayload,
            settings=cfg,
        )
    except Exception:  # noqa: BLE001
        return None

    variants: list[PlanProposal] = []
    for variant_name, course_ids in (
        ("primary", payload.primary or primary.course_ids),
        ("alternate_safe", payload.alternate_safe),
        ("alternate_progress", payload.alternate_progress),
    ):
        normalized = _normalize_course_ids(course_ids)
        if not normalized:
            continue

        verified, _refs = filter_eligible_courses(
            engine=engine,
            technion_raw_dir=technion_raw_dir,
            course_ids=normalized,
            completed_courses=completed_courses,
            semester_filename=primary.semester_filename,
        )
        if not verified:
            continue

        total_credits = sum(parse_course_credits(engine, course_id) for course_id in verified)
        if total_credits > max_credits:
            continue

        variants.append(
            PlanProposal(
                course_ids=verified,
                semester_filename=primary.semester_filename,
                notes=payload.notes or f"LLM-synthesized {variant_name} variant.",
                variant=variant_name,
            )
        )

    if not variants:
        return None

    seen: set[tuple[str, ...]] = set()
    unique: list[PlanProposal] = []
    for variant in variants:
        key = tuple(variant.course_ids)
        if key in seen:
            continue
        seen.add(key)
        unique.append(variant)
    return unique if len(unique) >= 2 else None
