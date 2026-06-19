from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.db.mongo import check_mongo_connectivity
from app.db.redis import check_redis_connectivity

router = APIRouter(tags=["health"])


def resolve_service_status(mongo_status: str, redis_status: str) -> str:
    configured_statuses = [
        status
        for status in (mongo_status, redis_status)
        if status not in ("not_configured",)
    ]

    if not configured_statuses:
        return "ok"

    if any(status == "disconnected" for status in configured_statuses):
        return "degraded"

    return "ok"


@router.get("/health")
async def get_health() -> dict:
    settings = get_settings()
    mongo_status = await check_mongo_connectivity()
    redis_status = await check_redis_connectivity()

    return {
        "service": settings.service_name,
        "status": resolve_service_status(mongo_status, redis_status),
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "mongo": mongo_status,
            "redis": redis_status,
        },
    }
