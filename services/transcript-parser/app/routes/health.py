"""Health routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.core.responses import success_response

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return success_response(
        {
            "service": settings.service_name,
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
