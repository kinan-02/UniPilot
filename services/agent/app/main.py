"""UniPilot Agent service — internal-only, never exposed to the host."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.mongo import close_mongo_client
from app.routes.health import router as health_router
from app.routes.turn import router as turn_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_mongo_client()


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.environment == "production"
    app = FastAPI(
        title="UniPilot Agent Service",
        description="Internal conversational agent service (intent, retrieval, reasoning, workflows)",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(health_router)
    app.include_router(turn_router)
    return app


async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "data": None, "error": "Validation failed", "errors": exc.errors()},
    )


async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": detail},
    )


app = create_app()
