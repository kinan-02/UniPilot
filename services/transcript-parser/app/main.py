"""Transcript parser FastAPI application."""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.routes.health import router as health_router
from app.routes.parse import router as parse_router


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.environment == "production"
    app = FastAPI(
        title="UniPilot Transcript Parser",
        description="Internal service for Technion official transcript PDF extraction",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(health_router)
    app.include_router(parse_router)
    return app


async def validation_exception_handler(_request, exc: RequestValidationError):
    return _error_response(status_code=400, detail="Validation failed", errors=exc.errors())


async def http_exception_handler(_request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(status_code=exc.status_code, detail=detail)


def _error_response(*, status_code: int, detail: str, errors: list | None = None):
    from fastapi.responses import JSONResponse

    payload = {
        "success": False,
        "data": None,
        "error": detail,
    }
    if errors is not None:
        payload["errors"] = errors
    return JSONResponse(status_code=status_code, content=payload)


app = create_app()
