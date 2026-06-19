from fastapi import FastAPI

from app.core.errors import unhandled_exception_handler
from app.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="UniPilot API (Python)",
        description="FastAPI backend for UniPilot AI — migration target",
        version="0.1.0",
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    return app


app = create_app()
