from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.mongo import check_mongo_connectivity

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health() -> JSONResponse:
    settings = get_settings()
    mongo_status = await check_mongo_connectivity()
    service_status = "ok" if mongo_status in ("connected", "not_configured") else "degraded"

    payload = {
        "service": settings.service_name,
        "status": service_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {"mongo": mongo_status},
    }
    if settings.environment != "production":
        payload["environment"] = settings.environment

    status_code = 200 if service_status == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)
