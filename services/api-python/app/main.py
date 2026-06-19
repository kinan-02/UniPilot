from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.errors import unhandled_exception_handler
from app.db.mongo import close_mongo_client
from app.routes.health import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_mongo_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="UniPilot API (Python)",
        description="FastAPI backend for UniPilot AI — migration target",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    return app


app = create_app()
