from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db.mongo import close_mongo_client
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.student_profile import router as student_profile_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.require_jwt_secret()
    yield
    close_mongo_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="UniPilot API (Python)",
        description="FastAPI backend for UniPilot AI — migration target",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(student_profile_router)
    return app


app = create_app()
