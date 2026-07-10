"""Health routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.retrieval.graph_engine.graph_registry import graph_registry

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    stats = graph_registry.cached_stats()
    return {
        "service": "ai",
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "academic_graph": stats,
    }
