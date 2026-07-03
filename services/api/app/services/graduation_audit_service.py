"""Deterministic graduation audit for the UniPilot Agent (spec §30.1)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.agent.schemas import AgentContextPack
from app.services.graduation_progress_service import get_graduation_progress_for_user

AuditStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
    "audit_failed",
]


class GraduationAuditResult(BaseModel):
    status: AuditStatus
    progress: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    graduation_status: str = "missing_data"
    can_graduate: bool = False


def _map_graduation_status(status_summary: str | None, *, credits_remaining: float | None) -> str:
    normalized = str(status_summary or "").strip()
    if normalized == "complete":
        return "ready_to_graduate"
    if normalized in {"in_progress", "mandatory_requirements_met"}:
        if credits_remaining is not None and credits_remaining <= 0:
            return "needs_review"
        return "not_ready"
    if normalized == "not_started":
        return "not_ready"
    return "needs_review"


def _extract_blockers(progress: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    mandatory = progress.get("remainingMandatoryCourses") or []
    if mandatory:
        labels = [
            str(course.get("courseNumber") or course.get("courseTitle") or course.get("courseId") or "")
            for course in mandatory
            if isinstance(course, dict)
        ]
        labels = [label for label in labels if label]
        if labels:
            blockers.append(
                f"Missing mandatory course(s): {', '.join(labels[:6])}"
                + ("…" if len(labels) > 6 else "")
            )
        else:
            blockers.append(f"Missing {len(mandatory)} mandatory course(s)")

    missing_requirements = progress.get("missingRequirements") or []
    unsatisfied = [
        entry
        for entry in missing_requirements
        if isinstance(entry, dict) and entry.get("status") != "satisfied"
    ]
    for entry in unsatisfied[:5]:
        title = str(entry.get("title") or entry.get("requirementGroupId") or "Requirement")
        remaining = entry.get("creditsRemaining")
        if remaining:
            blockers.append(f"{title}: {remaining} credits remaining")
        else:
            blockers.append(f"{title} is not satisfied")

    if progress.get("ineligibleCredits"):
        blockers.append(
            f"{len(progress['ineligibleCredits'])} completed course(s) did not count toward requirements"
        )

    return blockers


async def run_graduation_audit(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    context: AgentContextPack | None = None,
) -> GraduationAuditResult:
    """Run deterministic graduation audit; optionally cross-check retrieved context."""
    raw = await get_graduation_progress_for_user(database, user_id)
    status = str(raw.get("status") or "audit_failed")

    if status != "ok":
        return GraduationAuditResult(
            status=status,  # type: ignore[arg-type]
            errors=[_status_error_message(status)],
            graduation_status="missing_data",
        )

    progress = raw.get("progress") or {}
    warnings: list[str] = []
    if context is not None:
        warnings.extend(context.validation.warnings)
        data_quality = (context.user_context.get("dataQuality") or {}).get("warnings") or []
        warnings.extend(str(item) for item in data_quality)

    advisory = progress.get("advisoryWarnings") or []
    warnings.extend(str(item) for item in advisory if item)

    assumptions = list(progress.get("assumptions") or [])
    blockers = _extract_blockers(progress)
    credits_remaining = progress.get("creditsRemaining")
    graduation_status = _map_graduation_status(
        progress.get("statusSummary"),
        credits_remaining=float(credits_remaining) if credits_remaining is not None else None,
    )
    can_graduate = graduation_status == "ready_to_graduate" and not blockers

    if context is not None and context.user_context.get("profile") is None:
        warnings.append("profile_missing_in_context_pack")

    return GraduationAuditResult(
        status="ok",
        progress=progress,
        warnings=_dedupe(warnings),
        assumptions=assumptions,
        blockers=blockers,
        graduation_status=graduation_status,
        can_graduate=can_graduate,
    )


def _status_error_message(status: str) -> str:
    mapping = {
        "profile_not_found": "Student profile not found",
        "degree_not_selected": "Degree program not selected on profile",
        "degree_not_found": "Degree program not found in catalog",
    }
    return mapping.get(status, f"Graduation audit failed: {status}")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered
