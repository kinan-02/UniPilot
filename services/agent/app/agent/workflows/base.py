"""Workflow execution contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent


class AgentWorkflow(Protocol):
    name: str

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        ...
