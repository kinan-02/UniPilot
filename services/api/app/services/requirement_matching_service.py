"""Requirement matching for agent graduation workflow (spec §30.1 step 7)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RequirementMatchEntry(BaseModel):
    requirement_group_id: str
    title: str | None = None
    status: str
    credits_completed: float = 0.0
    credits_required: float = 0.0
    credits_remaining: float = 0.0
    remaining_course_count: int = 0
    catalog_matched: bool = True


class RequirementMatchingSummary(BaseModel):
    total_requirements: int = 0
    satisfied_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    coverage_percentage: float = 0.0
    entries: list[RequirementMatchEntry] = Field(default_factory=list)
    unmatched_catalog_rules: list[str] = Field(default_factory=list)


def match_degree_requirements(
    *,
    progress: dict[str, Any],
    catalog_requirements: list[dict[str, Any]] | None = None,
) -> RequirementMatchingSummary:
    """Align calculated requirement progress with catalog requirement rules."""
    requirement_progress = [
        entry for entry in (progress.get("requirementProgress") or []) if isinstance(entry, dict)
    ]
    entries: list[RequirementMatchEntry] = []
    satisfied = partial = missing = 0

    for entry in requirement_progress:
        status = str(entry.get("status") or "missing")
        if status == "satisfied":
            satisfied += 1
        elif status in {"in_progress", "partial"}:
            partial += 1
        else:
            missing += 1

        entries.append(
            RequirementMatchEntry(
                requirement_group_id=str(entry.get("requirementGroupId") or ""),
                title=entry.get("title"),
                status=status,
                credits_completed=float(entry.get("creditsCompleted") or 0),
                credits_required=float(entry.get("minCredits") or entry.get("creditsRequired") or 0),
                credits_remaining=float(entry.get("creditsRemaining") or 0),
                remaining_course_count=len(entry.get("remainingCourses") or []),
                catalog_matched=True,
            )
        )

    catalog_ids = {
        str(rule.get("requirementGroupId") or "")
        for rule in (catalog_requirements or [])
        if isinstance(rule, dict) and rule.get("requirementGroupId")
    }
    progress_ids = {entry.requirement_group_id for entry in entries if entry.requirement_group_id}
    unmatched = sorted(catalog_id for catalog_id in catalog_ids if catalog_id not in progress_ids)

    total = len(entries)
    coverage = round((satisfied / total) * 100, 1) if total else 0.0

    return RequirementMatchingSummary(
        total_requirements=total,
        satisfied_count=satisfied,
        partial_count=partial,
        missing_count=missing,
        coverage_percentage=coverage,
        entries=entries,
        unmatched_catalog_rules=unmatched,
    )
