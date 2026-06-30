"""UniPilot AI FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.responses import error_response
from app.routes.advisor import router as advisor_router
from app.routes.health import router as health_router
from app.services.graph_registry import graph_registry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    graph_registry.refresh_stats(get_settings())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.environment == "production"
    app = FastAPI(
        title="UniPilot AI Service",
        description="Internal academic advisor and graph retrieval service",
        version="0.2.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(health_router)
    app.include_router(advisor_router)
    return app


async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    payload = error_response("Validation failed")
    payload["errors"] = exc.errors()
    return JSONResponse(status_code=400, content=payload)


async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    payload = error_response(detail)
    return JSONResponse(status_code=exc.status_code, content=payload)


app = create_app()
