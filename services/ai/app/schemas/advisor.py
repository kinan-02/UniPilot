"""Request/response schemas for advisor routes."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TranscriptEntryPayload(BaseModel):
    course_number: str
    semester_code: str | None = None
    grade: str | None = None
    credits_earned: float | None = None


class UserContextPayload(BaseModel):
    track_slug: str | None = None
    faculty: str | None = None
    catalog_year: int | None = None
    completed_courses: list[str] = Field(default_factory=list)
    display_name: str | None = None
    degree_id: str | None = None
    semester_filename: str | None = None
    plan_semester_code: str | None = None
    institution_id: str | None = None
    program_type: str | None = None
    academic_path: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    transcript: list[TranscriptEntryPayload] = Field(default_factory=list)
    planning_context: dict[str, Any] = Field(default_factory=dict)


class RetrieveRequest(BaseModel):
    intent: Literal[
        "schedule",
        "structure",
        "eligibility",
        "syllabus",
        "prerequisites",
        "course_info",
        "wiki_page",
        "wiki_search",
    ]
    course_id: str | None = None
    user_completed_courses: list[str] = Field(default_factory=list)
    wiki_slug: str | None = None
    search_query: str | None = None
    semester_filename: str | None = None


class AdviseRequest(BaseModel):
    question: str = Field(min_length=1)
    user_context: UserContextPayload = Field(default_factory=UserContextPayload)


class SummarizeConversationRequest(BaseModel):
    previous_summary: str | None = None
    user_message: str = Field(min_length=1)
    advisor_answer: str = Field(min_length=1)


class GraphActionResult(BaseModel):
    success: bool
    data: dict[str, Any] | list[Any] | str | None = None
    error: str | None = None
