"""Explainer LLM layer — student-facing summary from negotiation artifacts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.llm.structured_output import invoke_structured_model
from app.orchestrator.artifacts import StudentSummary
from app.orchestrator.types import PlanProposal


class _SummaryPayload(BaseModel):
    headline: str
    rationale: str
    trade_offs: list[str] = Field(default_factory=list)


def build_deterministic_summary(
    *,
    goal: str,
    proposal: PlanProposal,
    final_decision: dict[str, Any],
    soft_critiques: list[dict[str, Any]],
) -> StudentSummary:
    course_ids = list(proposal.course_ids)
    headline = (
        f"Recommended {len(course_ids)} course(s) for your goal."
        if course_ids
        else "No feasible courses could be committed."
    )
    semester = final_decision.get("semesterLabel")
    rationale_parts = [f"Goal: {goal}"]
    if semester:
        rationale_parts.append(f"Semester: {semester}")
    if course_ids:
        rationale_parts.append(f"Courses: {', '.join(course_ids)}")

    trade_offs = [
        str(critique.get("message") or critique.get("type") or "")
        for critique in soft_critiques
        if critique.get("message") or critique.get("type")
    ]

    return StudentSummary(
        headline=headline,
        rationale=" ".join(rationale_parts),
        trade_offs=trade_offs[:5],
        source="deterministic",
    )


async def explain_decision_with_llm(
    *,
    goal: str,
    proposal: PlanProposal,
    final_decision: dict[str, Any],
    transcript: list[dict[str, Any]],
    soft_critiques: list[dict[str, Any]],
    settings: Settings | None = None,
) -> StudentSummary:
    """Layer 2 — narration only; cannot change the committed plan."""
    cfg = settings or get_settings()
    base = build_deterministic_summary(
        goal=goal,
        proposal=proposal,
        final_decision=final_decision,
        soft_critiques=soft_critiques,
    )
    if not cfg.llm_configured():
        return base

    roles = [turn.get("agent_role") for turn in transcript[-8:]]
    try:
        payload = await invoke_structured_model(
            system_prompt=(
                "You are the UniPilot Explainer. Write a concise student-facing summary of "
                "a completed multi-agent semester planning session. Use only facts from the "
                "provided artifacts. Do not invent courses or change the plan."
            ),
            user_prompt=(
                f"Goal: {goal}\n"
                f"Committed courses: {', '.join(proposal.course_ids)}\n"
                f"Utility: {final_decision.get('utilityBreakdown', {}).get('utility', 'n/a')}\n"
                f"Soft critiques: {soft_critiques}\n"
                f"Recent agent roles: {roles}\n"
                'Return JSON: {"headline":"...", "rationale":"...", "trade_offs":["..."]}'
            ),
            model_type=_SummaryPayload,
            settings=cfg,
        )
        return StudentSummary(
            headline=payload.headline or base.headline,
            rationale=payload.rationale or base.rationale,
            trade_offs=payload.trade_offs or base.trade_offs,
            source="llm",
        )
    except Exception:  # noqa: BLE001
        return base
