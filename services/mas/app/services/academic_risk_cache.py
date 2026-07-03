"""Shared academic-risk preview cache for MAS negotiation."""

from __future__ import annotations

import asyncio
from typing import Any

from app.clients.academic_risk_client import fetch_academic_risk_preview
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.plan_risk import resolve_max_credits


def academic_risk_cache_key(course_ids: list[str]) -> str:
    return ",".join(sorted(dict.fromkeys(str(course_id) for course_id in course_ids if course_id)))


def get_cached_academic_risk(
    blackboard: Blackboard,
    course_ids: list[str],
) -> dict[str, Any] | None:
    if not course_ids:
        return None
    key = academic_risk_cache_key(course_ids)
    cached = blackboard.academic_risk_cache.get(key)
    return cached if isinstance(cached, dict) else None


async def _fetch_one(
    blackboard: Blackboard,
    course_ids: list[str],
) -> tuple[str, dict[str, Any] | None]:
    user_id = str(blackboard.user_context.get("user_id") or "")
    if not user_id:
        return academic_risk_cache_key(course_ids), None

    semester_code = str(blackboard.user_context.get("plan_semester_code") or "2025-1")
    constraints = blackboard.user_context.get("constraints") or {}
    min_credits = constraints.get("minCredits")
    analysis = await fetch_academic_risk_preview(
        user_id=user_id,
        course_numbers=list(course_ids),
        semester_code=semester_code,
        max_credits=resolve_max_credits(blackboard.user_context),
        min_credits=float(min_credits) if isinstance(min_credits, (int, float)) else None,
        settings=blackboard.settings,
    )
    return academic_risk_cache_key(course_ids), analysis


async def preload_academic_risk_cache(
    blackboard: Blackboard,
    proposals: list[PlanProposal],
) -> None:
    """Fetch academic-risk previews for unique variant course sets (parallel)."""
    unique_sets: dict[str, list[str]] = {}
    for proposal in proposals:
        if not proposal.course_ids:
            continue
        key = academic_risk_cache_key(proposal.course_ids)
        if key not in unique_sets:
            unique_sets[key] = list(proposal.course_ids)

    pending = [
        course_ids
        for key, course_ids in unique_sets.items()
        if key not in blackboard.academic_risk_cache
    ]
    if not pending:
        return

    results = await asyncio.gather(
        *[_fetch_one(blackboard, course_ids) for course_ids in pending],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            continue
        key, analysis = result
        if analysis is not None:
            blackboard.academic_risk_cache[key] = analysis


async def fetch_and_cache_academic_risk(
    blackboard: Blackboard,
    course_ids: list[str],
) -> dict[str, Any] | None:
    """Return cached or freshly fetched academic-risk preview."""
    cached = get_cached_academic_risk(blackboard, course_ids)
    if cached is not None:
        return cached

    _key, analysis = await _fetch_one(blackboard, course_ids)
    if analysis is not None:
        blackboard.academic_risk_cache[_key] = analysis
    return analysis
