"""Pydantic schemas for UniPilot Agent conversation API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateAgentConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)


class SendAgentMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class AgentConversationResponse(BaseModel):
    id: str
    userId: str
    title: str | None = None
    status: str
    entities: dict[str, Any] = Field(default_factory=dict)
    lastMessagePreview: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class AgentMessageResponse(BaseModel):
    id: str
    conversationId: str
    userId: str
    role: str
    content: str
    structuredBlocks: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    runId: str | None = None
    createdAt: str | None = None
