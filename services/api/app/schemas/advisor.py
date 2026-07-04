"""Advisor request/response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AskAdvisorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(
        default=None,
        description="Continue an existing summarized conversation, or omit to start a new one.",
    )
    include_agent_trace: bool = Field(
        default=False,
        description="When true, include internal retrieval/profile agent steps in the response.",
    )
    execution_mode: Literal["auto", "sync", "async"] = Field(
        default="auto",
        description=(
            "auto: offload heavy planning/degree questions to a background job; "
            "sync: always run immediately; async: always queue a background job."
        ),
    )


class AdvisorConversationPayload(BaseModel):
    id: str
    title: str
    summary: str
    exchange_count: int = Field(serialization_alias="exchangeCount")
    last_confidence: str | None = Field(default=None, serialization_alias="lastConfidence")
    created_at: str | None = Field(default=None, serialization_alias="createdAt")
    updated_at: str | None = Field(default=None, serialization_alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class AdvisorAnswerPayload(BaseModel):
    answer: str
    confidence: str = "medium"
    course_ids: list[str] = Field(default_factory=list)
    wiki_slugs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    eligibility: dict | None = None
