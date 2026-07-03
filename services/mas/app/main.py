"""UniPilot MAS FastAPI application."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.responses import error_response, success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.routes.health import router as health_router
from app.services.graph_registry import graph_registry
from app.sessions.processor import process_session
from app.worker import run_worker_loop

logger = logging.getLogger(__name__)
_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _worker_task
    graph_registry.refresh_stats(get_settings())
    settings = get_settings()
    if settings.mas_worker_enabled:
        _worker_task = asyncio.create_task(run_worker_loop())
    yield
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    from app.db.mongo import close_mongo_client
    from app.db.redis_client import close_redis_client

    await close_redis_client()
    close_mongo_client()


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.environment == "production"
    app = FastAPI(
        title="UniPilot MAS Service",
        description="Internal multi-agent orchestration runtime",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(health_router)

    @app.post(
        "/internal/sessions/{session_id}/process",
        dependencies=[Depends(require_internal_service_token)],
    )
    async def process_session_route(session_id: str) -> dict:
        try:
            session = await process_session(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return success_response({"session": _public_session(session)})

    return app


def _public_session(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "userId": str(document.get("userId")),
        "type": document.get("type"),
        "goal": document.get("goal"),
        "status": document.get("status"),
        "finalDecision": document.get("finalDecision"),
        "transcript": document.get("transcript") or [],
        "rounds": document.get("rounds", 0),
        "error": document.get("error"),
        "createdAt": document.get("createdAt"),
        "updatedAt": document.get("updatedAt"),
    }


async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    payload = error_response("Validation failed")
    payload["errors"] = exc.errors()
    return JSONResponse(status_code=400, content=payload)


async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    payload = error_response(detail)
    return JSONResponse(status_code=exc.status_code, content=payload)


app = create_app()
