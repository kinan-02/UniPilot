"""Health routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.services.graph_registry import graph_registry

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    stats = graph_registry.cached_stats()
    return {
        "service": "mas",
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker_enabled": settings.mas_worker_enabled,
        "llm_configured": settings.llm_configured(),
        "academic_graph": stats,
    }
