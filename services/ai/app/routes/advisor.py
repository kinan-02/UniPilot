"""Advisor retrieval and synthesis routes."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.responses import error_response, success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.advisor import AdviseRequest, RetrieveRequest
from app.services.graph_registry import graph_registry

router = APIRouter(tags=["advisor"])


@router.post("/retrieve", dependencies=[Depends(require_internal_service_token)])
async def retrieve(body: RetrieveRequest) -> dict:
    settings = get_settings()
    if not settings.is_graph_configured():
        raise HTTPException(
            status_code=503,
            detail="Academic graph paths are not configured",
        )

    try:
        context = graph_registry.retrieve_context(
            intent=body.intent,
            course_id=body.course_id,
            user_completed_courses=body.user_completed_courses,
            wiki_slug=body.wiki_slug,
            search_query=body.search_query,
            semester_filename=body.semester_filename,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 — return user-safe message to caller
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return success_response({"context": context})


@router.post("/advise", dependencies=[Depends(require_internal_service_token)])
async def advise_route(body: AdviseRequest) -> dict:
    settings = get_settings()
    if not settings.is_graph_configured():
        raise HTTPException(
            status_code=503,
            detail="Academic graph paths are not configured",
        )

    if not (settings.openai_api_key or "").strip():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured",
        )

    try:
        result = graph_registry.run_advise(
            question=body.question.strip(),
            user_context=body.user_context.model_dump(),
            settings=settings,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return success_response(result)


@router.post("/infer", dependencies=[Depends(require_internal_service_token)])
async def infer_stub() -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "message": "AI inference stub is active in skeleton mode.",
        },
    )
