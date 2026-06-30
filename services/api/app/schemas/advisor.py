"""Advisor request/response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class AskAdvisorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


class AdvisorAnswerPayload(BaseModel):
    answer: str
    confidence: str = "medium"
    course_ids: list[str] = Field(default_factory=list)
    wiki_slugs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    eligibility: dict | None = None
