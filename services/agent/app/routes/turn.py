"""Internal-only endpoint that runs one agent turn (spec §7).

Called exclusively by `api`'s `agent_conversation_service.stream_message_turn`
after it has authenticated the student, persisted their message, and
resolved the trigger message id. This service never sees a user JWT.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.orchestrator import run_agent_turn
from app.agent.streaming import format_sse_event
from app.db.mongo import get_database
from app.dependencies.internal_auth import require_internal_service_token

router = APIRouter(tags=["turn"], dependencies=[Depends(require_internal_service_token)])


class AgentTurnRequest(BaseModel):
    user_id: str = Field(alias="userId")
    conversation_id: str = Field(alias="conversationId")
    user_message: str = Field(alias="userMessage")
    trigger_message_id: str = Field(alias="triggerMessageId")
    message_attachments: list[dict[str, Any]] = Field(default_factory=list, alias="messageAttachments")

    model_config = {"populate_by_name": True}


async def _stream_turn(payload: AgentTurnRequest):
    database = await get_database()
    async for event in run_agent_turn(
        database,
        user_id=payload.user_id,
        conversation_id=payload.conversation_id,
        user_message=payload.user_message,
        trigger_message_id=payload.trigger_message_id,
        message_attachments=payload.message_attachments,
    ):
        yield format_sse_event(event)


@router.post("/turn")
async def run_turn(payload: AgentTurnRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_turn(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
