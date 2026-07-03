"""Planner repair LLM layer — minimal edits after hard vetoes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.llm.structured_output import invoke_structured_model
from app.orchestrator.artifacts import Violation
from app.orchestrator.violations import violation_messages
from app.orchestrator.types import PlanProposal


class _RepairPayload(BaseModel):
    course_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PlannerRepairResult(BaseModel):
    course_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""


def _normalize_course_ids(raw_ids: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in raw_ids:
        digits = "".join(character for character in str(raw) if character.isdigit())
        if len(digits) == 8:
            cleaned.append(digits)
    return list(dict.fromkeys(cleaned))


async def repair_plan_with_llm(
    *,
    goal: str,
    proposal: PlanProposal,
    violations: list[Violation],
    completed_courses: list[str],
    settings: Settings | None = None,
) -> PlannerRepairResult | None:
    """
    Layer 1.5 — suggest a minimal course-id repair after structured violations.

    Returns repair result or None when LLM is unavailable / fails.
    """
    cfg = settings or get_settings()
    if not cfg.llm_configured() or not proposal.course_ids:
        return None

    violation_text = "\n".join(f"- {message}" for message in violation_messages(violations))
    try:
        payload = await invoke_structured_model(
            system_prompt=(
                "You are the UniPilot Planner repair layer. Given a vetoed semester plan, "
                "propose the smallest edit (drop/replace courses) that likely fixes violations. "
                "Use ONLY 8-digit course codes from the current plan unless removing a course. "
                "Never invent new course codes."
            ),
            user_prompt=(
                f"Goal: {goal}\n"
                f"Current plan: {', '.join(proposal.course_ids)}\n"
                f"Completed courses: {', '.join(completed_courses) or 'none'}\n"
                f"Violations:\n{violation_text}\n"
                'Return JSON: {"course_ids":["..."], "reasoning":"..."}'
            ),
            model_type=_RepairPayload,
            settings=cfg,
        )
        repaired = _normalize_course_ids(payload.course_ids)
        if not repaired:
            return None
        return PlannerRepairResult(course_ids=repaired, reasoning=payload.reasoning.strip())
    except Exception:  # noqa: BLE001
        return None
