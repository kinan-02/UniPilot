"""Proactive watchdog orchestration (AGT-8)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.academic_risk_repository import find_academic_risk_analyses_by_user_id
from app.repositories.ai_recommendation_repository import (
    ensure_ai_recommendation_indexes,
    to_public_ai_recommendation,
    upsert_ai_recommendation,
)
from app.repositories.semester_plan_repository import (
    find_semester_plan_by_id_and_user_id,
    find_semester_plans_by_user_id,
)
from app.repositories.student_profile_repository import find_student_profile_by_user_id
from app.services.email_stub_service import send_watchdog_email_stub
from app.services.semester_plan_service import load_planning_context
from app.services.watchdog_checks import WatchdogNudge, collect_watchdog_nudges

logger = logging.getLogger(__name__)

WatchdogTrigger = Literal["profile_change", "new_plan", "weekly_cron"]


def _nudge_to_recommendation(
    nudge: WatchdogNudge,
    *,
    trigger: WatchdogTrigger,
) -> dict[str, Any]:
    return {
        "type": "watchdog_nudge",
        "nudgeType": nudge.nudge_type,
        "trigger": trigger,
        "severity": nudge.severity,
        "title": nudge.title,
        "body": nudge.body,
        "evidence": nudge.evidence,
        "planId": nudge.plan_id,
        "riskAnalysisId": nudge.risk_analysis_id,
        "dedupeKey": nudge.dedupe_key,
        "status": "active",
    }


async def run_watchdog_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    trigger: WatchdogTrigger,
    plan_id: str | None = None,
    user_email: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run deterministic watchdog checks and persist nudges."""
    settings = settings or get_settings()
    await ensure_ai_recommendation_indexes(database, settings=settings)
    profile = await find_student_profile_by_user_id(database, user_id)
    if not profile:
        return {"status": "profile_not_found", "nudges": []}

    planning_context = await load_planning_context(database, user_id)
    if planning_context.get("status") != "ok":
        return {"status": planning_context.get("status"), "nudges": []}

    latest_plan = None
    if plan_id:
        latest_plan = await find_semester_plan_by_id_and_user_id(database, plan_id, user_id)
    if latest_plan is None:
        plans_page = await find_semester_plans_by_user_id(database, user_id, page=1, limit=1)
        plans = plans_page.get("plans") or []
        latest_plan = plans[0] if plans else None

    risks_page = await find_academic_risk_analyses_by_user_id(database, user_id, page=1, limit=5)
    latest_risk = None
    for analysis in risks_page.get("analyses") or []:
        if analysis.get("status") == "open" and (analysis.get("summary") or {}).get(
            "highestSeverity"
        ) == "high":
            latest_risk = analysis
            break

    nudges = collect_watchdog_nudges(
        profile=profile,
        graduation_progress=planning_context["graduationProgress"],
        semester_matrix_documents=planning_context.get("semesterMatrixDocuments") or [],
        latest_plan=latest_plan,
        latest_risk_analysis=latest_risk,
        planning_context=planning_context,
    )

    stored: list[dict[str, Any]] = []
    for nudge in nudges:
        document = await upsert_ai_recommendation(
            database,
            user_id,
            _nudge_to_recommendation(nudge, trigger=trigger),
            settings=settings,
        )
        public = to_public_ai_recommendation(document)
        if public:
            stored.append(public)
            if user_email:
                send_watchdog_email_stub(
                    user_id=user_id,
                    email=user_email,
                    title=nudge.title,
                    body=nudge.body,
                    metadata={"trigger": trigger, "dedupeKey": nudge.dedupe_key},
                )

    return {
        "status": "ok",
        "trigger": trigger,
        "nudgeCount": len(stored),
        "nudges": stored,
    }


async def run_weekly_watchdog_for_all_users(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Enqueue watchdog scans for users with profiles (internal cron entrypoint)."""
    from app.services.watchdog_enqueue import enqueue_watchdog_scan

    settings = settings or get_settings()
    from app.repositories.student_profile_repository import STUDENT_PROFILES_COLLECTION

    profile_collection = database[STUDENT_PROFILES_COLLECTION]
    cursor = profile_collection.find(
        {"degreeId": {"$ne": None}},
        {"userId": 1},
        limit=limit,
    )
    user_ids = [str(document["userId"]) async for document in cursor]

    queued = 0
    for user_id in user_ids:
        try:
            await enqueue_watchdog_scan(
                database,
                user_id,
                trigger="weekly_cron",
                settings=settings,
            )
            queued += 1
        except Exception:
            logger.exception("Failed to enqueue weekly watchdog scan for user %s", user_id)

    return {"status": "ok", "queued": queued, "eligibleUsers": len(user_ids)}
