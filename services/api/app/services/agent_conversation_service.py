from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.orchestrator import run_agent_turn
from app.agent.schemas import StreamEvent
from app.agent.streaming import format_sse_event
from app.repositories.agent_conversation_repository import (
    create_agent_conversation,
    find_conversation_by_id_and_user,
    list_conversations_by_user,
    update_conversation_preview,
)
from app.repositories.agent_message_repository import (
    create_agent_message,
    list_messages_for_conversation,
)
from app.repositories.agent_run_repository import complete_agent_run


async def start_conversation(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    title: str | None = None,
) -> dict:
    return await create_agent_conversation(database, user_id=user_id, title=title)


async def get_conversation_for_user(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
) -> dict | None:
    return await find_conversation_by_id_and_user(database, conversation_id, user_id)


async def list_conversations_for_user(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    return await list_conversations_by_user(database, user_id, limit=limit)


async def get_messages_for_conversation(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
) -> list[dict]:
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    if conversation is None:
        return []
    return await list_messages_for_conversation(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
    )


async def stream_message_turn(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    content: str,
    attachments: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    if conversation is None:
        yield format_sse_event(StreamEvent(type="run.failed", error="Conversation not found"))
        return

    user_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=content.strip(),
        attachments=attachments,
    )
    await update_conversation_preview(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        preview=content.strip(),
    )

    async for event in run_agent_turn(
        database,
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=content.strip(),
        trigger_message_id=str(user_message["id"]),
        message_attachments=list(attachments or []),
    ):
        yield format_sse_event(event)


async def cancel_conversation_run(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    run_id: str,
) -> bool:
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    if conversation is None:
        return False
    await complete_agent_run(
        database,
        run_id=run_id,
        user_id=user_id,
        status="cancelled",
    )
    return True
