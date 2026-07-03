"""JWT-protected MAS agent session routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit
from app.schemas.agent_session import (
    ApplyAgentSessionRequest,
    ClarifyAgentSessionRequest,
    CreateAgentSessionRequest,
    OverrideAgentSessionRequest,
    WhyAgentSessionRequest,
    SecondOpinionAgentSessionRequest,
)
from app.services.agent_session_service import (
    get_agent_session_for_user,
    list_agent_sessions_for_user,
    start_agent_session,
)
from app.services.agent_session_clarify_service import clarify_agent_session
from app.services.agent_session_replay_service import get_agent_session_replay_for_user
from app.services.agent_session_stream_service import stream_agent_session_events_for_user
from app.services.agent_session_second_opinion_service import start_second_opinion_session
from app.services.agent_session_why_service import explain_agent_session_why_for_user
from app.services.agent_session_apply_service import (
    apply_agent_session_to_plan,
    approve_agent_session,
    override_agent_session,
)

router = APIRouter(prefix="/agent/sessions", tags=["agent-sessions"])


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.post("", status_code=202)
async def create_agent_session_route(
    request: Request,
    payload: CreateAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> Response:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    session = await start_agent_session(
        database,
        user_id=auth.user_id,
        session_type=payload.type,
        goal=payload.goal.strip(),
        constraints=payload.constraints,
    )
    body = success_response({"session": session})
    return JSONResponse(status_code=202, content=body)


@router.get("/{session_id}")
async def get_agent_session_route(
    session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    session = await get_agent_session_for_user(
        database,
        user_id=auth.user_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return success_response({"session": session})


@router.get("")
async def list_agent_sessions_route(
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    sessions = await list_agent_sessions_for_user(database, user_id=auth.user_id)
    return success_response({"sessions": sessions})


@router.get("/{session_id}/replay")
async def get_agent_session_replay_route(
    session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await get_agent_session_replay_for_user(
        database,
        user_id=auth.user_id,
        session_id=session_id,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    return success_response(
        {
            "events": result.get("events") or [],
            "replayAvailable": bool(result.get("replayAvailable")),
        }
    )


@router.get("/{session_id}/stream")
async def stream_agent_session_route(
    session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> StreamingResponse:
    database = await get_database()

    async def event_generator():
        async for chunk in stream_agent_session_events_for_user(
            database,
            user_id=auth.user_id,
            session_id=session_id,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/second-opinion", status_code=202)
async def second_opinion_agent_session_route(
    request: Request,
    session_id: str,
    payload: SecondOpinionAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> Response:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await start_second_opinion_session(
        database,
        user_id=auth.user_id,
        session_id=session_id,
        utility_profile=payload.utility_profile,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] == "invalid_state":
        raise HTTPException(status_code=400, detail=result.get("error"))
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})
    body = success_response(
        {
            "session": result["session"],
            "utilityProfile": result.get("utilityProfile"),
            "sourceSessionId": result.get("sourceSessionId"),
        }
    )
    return JSONResponse(status_code=202, content=body)


@router.post("/{session_id}/why")
async def why_agent_session_route(
    request: Request,
    session_id: str,
    payload: WhyAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    result = await explain_agent_session_why_for_user(
        database,
        user_id=auth.user_id,
        session_id=session_id,
        question=payload.question.strip(),
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})
    return success_response(
        {
            "question": result.get("question"),
            "answer": result.get("answer"),
            "citations": result.get("citations") or [],
            "topics": result.get("topics") or [],
            "source": result.get("source"),
        }
    )


@router.post("/{session_id}/clarify")
async def clarify_agent_session_route(
    session_id: str,
    payload: ClarifyAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await clarify_agent_session(
        database,
        user_id=auth.user_id,
        session_id=session_id,
        clarification=payload.clarification.strip(),
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] == "invalid_state":
        raise HTTPException(status_code=409, detail=result.get("error"))
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})
    return success_response({"session": result["session"]})


@router.post("/{session_id}/approve")
async def approve_agent_session_route(
    session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await approve_agent_session(
        database,
        user_id=auth.user_id,
        session_id=session_id,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] == "invalid_state":
        raise HTTPException(status_code=409, detail=result.get("error"))
    return success_response({"session": result["session"]})


@router.post("/{session_id}/override")
async def override_agent_session_route(
    session_id: str,
    payload: OverrideAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await override_agent_session(
        database,
        user_id=auth.user_id,
        session_id=session_id,
        course_ids=payload.course_ids,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] == "invalid_state":
        raise HTTPException(status_code=409, detail=result.get("error"))
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})
    return success_response({"session": result["session"]})


@router.post("/{session_id}/apply")
async def apply_agent_session_route(
    session_id: str,
    payload: ApplyAgentSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    result = await apply_agent_session_to_plan(
        database,
        user_id=auth.user_id,
        session_id=session_id,
        plan_name=payload.name,
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Agent session not found")
    if result["status"] in {"invalid_state", "approval_required", "already_applied"}:
        raise HTTPException(status_code=409, detail=result.get("error"))
    if result["status"] == "validation_error":
        raise HTTPException(status_code=400, detail={"errors": result.get("errors", [])})
    if result["status"] == "profile_not_found":
        raise HTTPException(
            status_code=400,
            detail="Student profile is required before creating a semester plan.",
        )
    if result["status"] != "ok":
        errors = result.get("errors")
        raise HTTPException(
            status_code=400,
            detail=errors if errors else result.get("error", "Apply failed"),
        )
    return success_response(
        {
            "session": result["session"],
            "semesterPlanId": result["semesterPlanId"],
            "skippedCourses": result.get("skippedCourses") or [],
        }
    )
