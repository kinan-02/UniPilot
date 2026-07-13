"""JWT-protected advisor routes (proxies internal AI service)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.schemas.advisor import AskAdvisorRequest
from app.services.advisor_service import ask_advisor_for_user, stream_advisor_for_user

router = APIRouter(prefix="/advisor", tags=["advisor"])


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.post("/ask")
async def ask_advisor_route(
    request: Request,
    payload: AskAdvisorRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await ask_advisor_for_user(
        database,
        auth.user_id,
        payload.question.strip(),
    )

    status = result.get("status")
    if status == "unavailable":
        raise HTTPException(status_code=503, detail=result.get("detail", "Advisor unavailable"))
    if status == "bad_request":
        raise HTTPException(status_code=400, detail=result.get("detail", "Invalid advisor request"))
    if status == "error":
        raise HTTPException(status_code=502, detail=result.get("detail", "Advisor request failed"))

    return success_response({"advisor": result["advisor"]})

@router.post("/ask/stream")
async def stream_advisor_route(
    request: Request,
    payload: AskAdvisorRequest,
    auth: AuthContext = Depends(require_auth),
) -> StreamingResponse:
    await enforce_ai_rate_limit(request, auth.user_id)
    # We pass the generator to StreamingResponse
    return StreamingResponse(
        stream_advisor_for_user(auth.user_id, payload.question.strip()),
        media_type="text/event-stream"
    )
