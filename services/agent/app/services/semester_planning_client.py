"""Local client-side mirror of `api`'s `SemesterPlanningResult`.

Semester plan option generation (course selection, schedule building,
credit-variant logic) stays exclusively in `api` — see
`services/api/app/routes/internal_agent.py` — since it shares the same
planning engine (`semester_plan_suggestion_service`,
`manual_semester_plan_service`) used by `api`'s own plain
`/semester-plans/*` REST endpoints. This module calls that endpoint,
building its request body directly from the agent's own `AgentContextPack`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import AgentContextPack
from app.clients.internal_api_client import fetch_semester_plan_options

PlanningStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
    "validation_error",
    "no_options",
]


class SemesterPlanOption(BaseModel):
    optionId: str
    label: str
    description: str
    semesterCode: str
    maxCredits: float
    totalCredits: float
    courseCount: int
    plannedCourses: list[dict[str, Any]] = Field(default_factory=list)
    scheduleSelections: list[dict[str, Any]] = Field(default_factory=list)
    examSummary: dict[str, Any] = Field(default_factory=dict)
    skippedCourses: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    partialPlan: bool = False
    emptyPlan: bool = False


class SemesterPlanningResult(BaseModel):
    status: PlanningStatus = "ok"
    semesterCode: str | None = None
    options: list[SemesterPlanOption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _context_snapshot(context: AgentContextPack) -> dict[str, Any]:
    return {
        "intent": context.intent,
        "entities": context.entities,
        "user_context": context.user_context,
        "assumptions": context.assumptions,
        "validation": {
            "status": context.validation.status,
            "warnings": context.validation.warnings,
            "errors": context.validation.errors,
        },
    }


async def generate_semester_plan_options(
    *,
    user_id: str,
    context: AgentContextPack,
) -> SemesterPlanningResult:
    payload = await fetch_semester_plan_options(
        user_id=user_id,
        context_snapshot=_context_snapshot(context),
    )
    return SemesterPlanningResult.model_validate(payload)
