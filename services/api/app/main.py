from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db.mongo import close_mongo_client
from app.routes.auth import router as auth_router
from app.routes.catalog import router as catalog_router
from app.routes.completed_courses import router as completed_courses_router
from app.routes.graduation_progress import router as graduation_progress_router
from app.routes.health import router as health_router
from app.routes.academic_risks import router as academic_risks_router
from app.routes.semester_plans import router as semester_plans_router
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
        title="UniPilot API",
        description="FastAPI backend for UniPilot AI — academic decision support",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(student_profile_router)
    app.include_router(catalog_router)
    app.include_router(completed_courses_router)
    app.include_router(graduation_progress_router)
    app.include_router(semester_plans_router)
    app.include_router(academic_risks_router)
    return app


app = create_app()
