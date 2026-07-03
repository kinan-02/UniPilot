from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db.catalog_bootstrap import ensure_development_catalog
from app.db.catalog_indexes import ensure_catalog_indexes
from app.db.mongo import close_mongo_client, get_database
from app.db.redis import close_redis
from app.routes.advisor import router as advisor_router
from app.routes.agent_conversations import router as agent_conversations_router
from app.routes.agent_sessions import router as agent_sessions_router
from app.routes.auth import router as auth_router
from app.routes.catalog import router as catalog_router
from app.routes.completed_courses import router as completed_courses_router
from app.routes.graduation_progress import router as graduation_progress_router
from app.routes.health import router as health_router
from app.routes.academic_risks import router as academic_risks_router
from app.routes.semester_plans import router as semester_plans_router
from app.routes.student_profile import router as student_profile_router
from app.routes.transcript_import import router as transcript_import_router
from app.routes.internal_services import router as internal_services_router
from app.routes.outlook_integration import router as outlook_integration_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.validate_production_settings()
    database = await get_database()
    await ensure_development_catalog(database, settings)
    await ensure_catalog_indexes(database, settings=settings)
    yield
    await close_redis()
    close_mongo_client()


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.environment == "production"
    app = FastAPI(
        title="UniPilot API",
        description="FastAPI backend for UniPilot AI — academic decision support",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_cors_origins(),
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
    app.include_router(transcript_import_router)
    app.include_router(advisor_router)
    app.include_router(agent_conversations_router)
    app.include_router(agent_sessions_router)
    app.include_router(internal_services_router)
    app.include_router(outlook_integration_router)
    return app


app = create_app()
