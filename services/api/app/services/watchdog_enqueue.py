"""Enqueue proactive watchdog scans on the worker queue (AGT-8)."""

from __future__ import annotations

import logging
from typing import Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.schemas.ai_job import CreateAiJobRequest
from app.services.ai_job_service import create_job_for_user
from app.services.watchdog_service import run_watchdog_for_user

logger = logging.getLogger(__name__)

WatchdogTrigger = Literal["profile_change", "new_plan", "weekly_cron"]

_SYNC_TRIGGERS = frozenset({"profile_change", "new_plan"})


async def enqueue_watchdog_scan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    trigger: WatchdogTrigger,
    *,
    plan_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    payload: dict[str, object] = {"trigger": trigger}
    if plan_id:
        payload["planId"] = plan_id

    return await create_job_for_user(
        database,
        user_id,
        CreateAiJobRequest(type="watchdog_scan", payload=payload),
        settings=settings,
    )


async def maybe_enqueue_watchdog_scan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    trigger: WatchdogTrigger,
    *,
    plan_id: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Run or enqueue a watchdog scan; logs failures without raising."""
    settings = settings or get_settings()
    try:
        if trigger in _SYNC_TRIGGERS:
            # Run immediately so dashboard alerts appear without waiting on the worker.
            await run_watchdog_for_user(
                database,
                user_id,
                trigger=trigger,
                plan_id=plan_id,
                settings=settings,
            )
            return
        await enqueue_watchdog_scan(
            database,
            user_id,
            trigger,
            plan_id=plan_id,
            settings=settings,
        )
    except Exception:
        logger.exception(
            "Failed to run or enqueue watchdog scan user_id=%s trigger=%s plan_id=%s",
            user_id,
            trigger,
            plan_id,
        )
