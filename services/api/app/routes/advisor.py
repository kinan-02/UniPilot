"""JWT-protected advisor routes (proxies internal AI service)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.repositories.advisor_conversation_repository import (
    delete_advisor_conversation_for_user,
    ensure_advisor_conversation_indexes,
)
from app.repositories.ai_job_repository import ensure_ai_job_indexes
from app.schemas.advisor import AskAdvisorRequest
from app.schemas.semester_plan import OBJECT_ID_PATTERN
from app.services.advisor_conversation_service import (
    get_conversation_for_user,
    list_conversations_for_user,
)
from app.services.advisor_ask_orchestrator import ask_advisor_or_enqueue

router = APIRouter(prefix="/advisor", tags=["advisor"])

_advisor_conversation_indexes_ready = False
_ai_job_indexes_ready = False


def reset_advisor_conversation_indexes_state() -> None:
    global _advisor_conversation_indexes_ready, _ai_job_indexes_ready
    _advisor_conversation_indexes_ready = False
    _ai_job_indexes_ready = False


async def _ensure_advisor_conversation_indexes_once() -> None:
    global _advisor_conversation_indexes_ready

    if _advisor_conversation_indexes_ready:
        return

    database = await get_database()
    await ensure_advisor_conversation_indexes(database)
    _advisor_conversation_indexes_ready = True


async def _ensure_ai_job_indexes_once() -> None:
    global _ai_job_indexes_ready

    if _ai_job_indexes_ready:
        return

    database = await get_database()
    await ensure_ai_job_indexes(database)
    _ai_job_indexes_ready = True


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def _validate_conversation_id(conversation_id: str) -> str:
    if not OBJECT_ID_PATTERN.fullmatch(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation id")
    return conversation_id


@router.get("/conversations")
async def list_advisor_conversations_route(
    auth: AuthContext = Depends(require_auth),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=50),
) -> dict[str, Any]:
    await _ensure_advisor_conversation_indexes_once()
    database = await get_database()
    data = await list_conversations_for_user(
        database,
        auth.user_id,
        page=page,
        limit=limit,
    )
    return success_response(data)


@router.get("/conversations/{conversation_id}")
async def get_advisor_conversation_route(
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_advisor_conversation_indexes_once()
    conversation_id = _validate_conversation_id(conversation_id)
    database = await get_database()
    result = await get_conversation_for_user(database, auth.user_id, conversation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Advisor conversation not found")
    return success_response(result)


@router.delete("/conversations/{conversation_id}")
async def delete_advisor_conversation_route(
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_advisor_conversation_indexes_once()
    conversation_id = _validate_conversation_id(conversation_id)
    database = await get_database()
    deleted = await delete_advisor_conversation_for_user(
        database,
        auth.user_id,
        conversation_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Advisor conversation not found")
    return success_response({"deleted": True})


@router.post("/ask", response_model=None)
async def ask_advisor_route(
    request: Request,
    payload: AskAdvisorRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any] | JSONResponse:
    await enforce_ai_rate_limit(request, auth.user_id)
    await _ensure_advisor_conversation_indexes_once()
    await _ensure_ai_job_indexes_once()
    database = await get_database()
    conversation_id = payload.conversation_id
    if conversation_id:
        conversation_id = _validate_conversation_id(conversation_id)

    result = await ask_advisor_or_enqueue(
        database,
        auth.user_id,
        payload.question.strip(),
        conversation_id=conversation_id,
        include_agent_trace=payload.include_agent_trace,
        execution_mode=payload.execution_mode,
    )

    if result.get("status") == "queued":
        return JSONResponse(
            status_code=202,
            content=success_response(
                {
                    "asyncAccepted": True,
                    "offloadReason": result.get("offloadReason"),
                    "job": result["job"],
                }
            ),
        )

    status = result.get("status")
    if status == "conversation_not_found":
        raise HTTPException(status_code=404, detail="Advisor conversation not found")
    if status == "unavailable":
        raise HTTPException(status_code=503, detail=result.get("detail", "Advisor unavailable"))
    if status == "bad_request":
        raise HTTPException(status_code=400, detail=result.get("detail", "Invalid advisor request"))
    if status == "error":
        raise HTTPException(status_code=502, detail=result.get("detail", "Advisor request failed"))

    data: dict[str, Any] = {"advisor": result["advisor"], "asyncAccepted": False}
    if result.get("conversation"):
        data["conversation"] = result["conversation"]
    return success_response(data)
