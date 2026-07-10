"""Internal watchdog cron routes (worker / ops only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.db.mongo import get_database
from app.dependencies.internal_auth import require_internal_service_token
from app.services.watchdog_service import run_weekly_watchdog_for_all_users

router = APIRouter(prefix="/internal/watchdog", tags=["internal-watchdog"])


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.post("/weekly-scan")
async def weekly_watchdog_scan_route(
    _auth: None = Depends(require_internal_service_token),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    database = await get_database()
    result = await run_weekly_watchdog_for_all_users(database, limit=limit)
    return success_response(result)
