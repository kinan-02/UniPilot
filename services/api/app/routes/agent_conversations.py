"""JWT-protected UniPilot Agent conversation routes (spec §25)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies.auth import AuthContext, require_auth
from app.db.mongo import get_database
from app.middleware.auth_rate_limiter import enforce_ai_rate_limit, enforce_transcript_import_rate_limit
from app.repositories.agent_message_repository import create_agent_message
from app.schemas.agent_conversation import (
    CreateAgentConversationRequest,
    SendAgentMessageRequest,
)
from app.services.agent_action_service import (
    AgentActionError,
    build_import_success_text,
    build_plan_saved_text,
    confirm_agent_action,
    reject_agent_action,
)
from app.services.agent_attachment_service import build_transcript_attachment, is_pdf_upload
from app.services.agent_conversation_service import (
    cancel_conversation_run,
    get_conversation_for_user,
    get_messages_for_conversation,
    list_conversations_for_user,
    start_conversation,
    stream_message_turn,
)

router = APIRouter(prefix="/agent/conversations", tags=["agent-conversations"])


def success_response(data: Any) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
    }


@router.post("")
async def create_conversation_route(
    request: Request,
    payload: CreateAgentConversationRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    conversation = await start_conversation(
        database,
        user_id=auth.user_id,
        title=payload.title,
    )
    return success_response({"conversation": conversation})


@router.get("")
async def list_conversations_route(
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    conversations = await list_conversations_for_user(database, user_id=auth.user_id)
    return success_response({"conversations": conversations})


@router.get("/{conversation_id}")
async def get_conversation_route(
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    database = await get_database()
    conversation = await get_conversation_for_user(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await get_messages_for_conversation(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return success_response({"conversation": conversation, "messages": messages})


def _extract_upload_file(form: Any) -> UploadFile | None:
    upload = form.get("file")
    if upload is not None and hasattr(upload, "read"):
        return upload
    if hasattr(form, "multi_items"):
        for key, value in form.multi_items():
            if key == "file" and hasattr(value, "read"):
                return value
    return None


async def _parse_message_request(
    request: Request,
    *,
    user_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    content_type = (request.headers.get("content-type") or "").lower()
    attachments: list[dict[str, Any]] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        content = str(form.get("content") or "").strip()
        upload = _extract_upload_file(form)
        if upload is not None and is_pdf_upload(upload):
            await enforce_transcript_import_rate_limit(request, user_id)
            attachments.append(await build_transcript_attachment(upload))
        if not content:
            raise HTTPException(status_code=400, detail="Message content is required")
        return content, attachments

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    payload = SendAgentMessageRequest.model_validate(body)
    return payload.content.strip(), list(payload.attachments or [])


@router.post("/{conversation_id}/messages")
async def send_message_route(
    request: Request,
    conversation_id: str,
    auth: AuthContext = Depends(require_auth),
):
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    conversation = await get_conversation_for_user(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    content, attachments = await _parse_message_request(request, user_id=auth.user_id)

    accept = (request.headers.get("accept") or "").lower()
    wants_stream = "text/event-stream" in accept or request.query_params.get("stream") == "true"

    if wants_stream:
        return StreamingResponse(
            stream_message_turn(
                database,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                content=content,
                attachments=attachments,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    events: list[dict[str, Any]] = []
    final_text = ""
    message_id = None
    run_id = None
    final_blocks: list[dict[str, Any]] = []
    final_warnings: list[str] = []
    final_prompts: list[str] = []
    final_actions: list[dict[str, Any]] = []
    final_assumptions: list[str] = []
    final_sources: list[str] = []
    async for sse_chunk in stream_message_turn(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        content=content,
        attachments=attachments,
    ):
        for line in sse_chunk.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line.removeprefix("data: ").strip())
            except json.JSONDecodeError:
                continue
            events.append(data)
            if data.get("type") == "message.completed":
                final_text = str(data.get("text") or final_text)
                message_id = data.get("messageId")
                run_id = data.get("runId")
            if data.get("type") == "structured_output" and data.get("block"):
                final_blocks.append(data["block"])
            if data.get("type") == "action.proposed" and data.get("action"):
                final_actions.append(data["action"])
            if data.get("type") == "run.failed":
                raise HTTPException(
                    status_code=500,
                    detail=str(data.get("error") or "Agent run failed"),
                )

    return success_response(
        {
            "text": final_text,
            "messageId": message_id,
            "runId": run_id,
            "blocks": final_blocks,
            "warnings": final_warnings,
            "suggestedPrompts": final_prompts,
            "proposedActions": final_actions,
            "assumptions": final_assumptions,
            "usedSources": final_sources,
            "events": events,
        }
    )


@router.post("/{conversation_id}/runs/{run_id}/cancel")
async def cancel_run_route(
    request: Request,
    conversation_id: str,
    run_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    cancelled = await cancel_conversation_run(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        run_id=run_id,
    )
    if not cancelled:
        raise HTTPException(status_code=404, detail="Conversation or run not found")
    return success_response({"runId": run_id, "status": "cancelled"})


@router.post("/{conversation_id}/actions/{action_id}/confirm")
async def confirm_action_route(
    request: Request,
    conversation_id: str,
    action_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    conversation = await get_conversation_for_user(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        outcome = await confirm_agent_action(
            database,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            action_id=action_id,
        )
    except AgentActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    proposal = outcome.get("proposal") or {}
    action_type = str(proposal.get("type") or "")
    result = outcome.get("result") or {}

    if action_type == "save_semester_plan":
        plan = result.get("plan") or {}
        text = build_plan_saved_text(
            plan_name=plan.get("name") or proposal.get("title"),
            semester_code=(proposal.get("payload") or {}).get("semesterCode"),
        )
        block_type = "semester_plan_saved"
        block_data = {
            "message": block_type,
            "planId": plan.get("id"),
            "planName": plan.get("name"),
        }
        response_key = "planResult"
    else:
        text = build_import_success_text(
            created_count=int(result.get("createdCount") or 0),
            skipped_count=int(result.get("skippedCount") or 0),
        )
        block_type = "transcript_import_completed"
        block_data = {
            "message": block_type,
            "createdCount": result.get("createdCount"),
            "skippedCount": result.get("skippedCount"),
        }
        response_key = "importResult"

    assistant_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        role="assistant",
        content=text,
        structured_blocks=[
            {
                "type": "WarningBlock",
                "data": block_data,
            }
        ],
    )

    return success_response(
        {
            "proposal": proposal,
            response_key: result,
            "message": assistant_message,
            "text": text,
        }
    )


@router.post("/{conversation_id}/actions/{action_id}/reject")
async def reject_action_route(
    request: Request,
    conversation_id: str,
    action_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    await enforce_ai_rate_limit(request, auth.user_id)
    database = await get_database()
    conversation = await get_conversation_for_user(
        database,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        outcome = await reject_agent_action(
            database,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            action_id=action_id,
        )
    except AgentActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return success_response({"proposal": outcome.get("proposal")})
