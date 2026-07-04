"""Route-level orchestration for advisor ask (sync vs async offload)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.ai_job import CreateAiJobRequest
from app.services.advisor_async_classifier import classify_advisor_offload
from app.services.advisor_service import ask_advisor_for_user
from app.services.ai_job_service import create_job_for_user

ExecutionMode = Literal["auto", "sync", "async"]


def should_enqueue_advisor_job(question: str, execution_mode: ExecutionMode) -> tuple[bool, str | None]:
    if execution_mode == "sync":
        return False, None
    if execution_mode == "async":
        return True, "force_async"

    offload, reason = classify_advisor_offload(question)
    return offload, reason


async def ask_advisor_or_enqueue(
    database: AsyncIOMotorDatabase,
    user_id: str,
    question: str,
    *,
    conversation_id: str | None = None,
    include_agent_trace: bool = False,
    execution_mode: ExecutionMode = "auto",
) -> dict[str, Any]:
    """
    Run sync advisor or enqueue advisor_deep_plan when auto/async mode detects
    a heavy question.
    """
    trimmed = question.strip()
    enqueue, offload_reason = should_enqueue_advisor_job(trimmed, execution_mode)
    if enqueue:
        payload: dict[str, Any] = {
            "question": trimmed,
            "include_agent_trace": include_agent_trace,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        request = CreateAiJobRequest(type="advisor_deep_plan", payload=payload)
        queued = await create_job_for_user(database, user_id, request)
        return {
            "status": "queued",
            "job": queued["job"],
            "offloadReason": offload_reason,
        }

    return await ask_advisor_for_user(
        database,
        user_id,
        trimmed,
        conversation_id=conversation_id,
        include_agent_trace=include_agent_trace,
    )
