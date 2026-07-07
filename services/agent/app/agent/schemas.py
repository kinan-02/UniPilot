"""Shared agent schemas: context pack, responses, streaming events, UI blocks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentIntent = Literal[
    "graduation_progress_check",
    "transcript_import",
    "semester_plan_generation",
    "semester_plan_modification",
    "course_question",
    "requirement_explanation",
    "prerequisite_check",
    "catalog_search",
    "completed_courses_update",
    "profile_update",
    "program_minor_lookup",
    "track_structure_lookup",
    "regulation_lookup",
    "general_academic_question",
    "unknown_or_unsupported",
]

AgentRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "requires_user_confirmation",
]

AgentStepStatus = Literal["pending", "running", "completed", "failed"]

ConversationStatus = Literal["active", "archived"]

MessageRole = Literal["user", "assistant", "system", "tool"]

StreamEventType = Literal[
    "message.delta",
    "message.completed",
    "agent.step.started",
    "agent.step.completed",
    "agent.step.failed",
    "tool.started",
    "tool.completed",
    "structured_output",
    "action.proposed",
    "run.completed",
    "run.failed",
]

BlockType = Literal[
    "RequirementSummaryBlock",
    "RequirementBucketBlock",
    "CourseRecommendationBlock",
    "PrerequisiteStatusBlock",
    "OfferingStatusBlock",
    "TranscriptReviewBlock",
    "SemesterPlanOptionsBlock",
    "SchedulePreviewBlock",
    "WarningBlock",
    "ConfirmationBlock",
    "SourceSummaryBlock",
]


class IntentClassification(BaseModel):
    intent: AgentIntent
    confidence: float = Field(ge=0.0, le=1.0)
    requires_file: bool = False
    requires_confirmation: bool = False
    required_context: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    workflow: str
    read_only: bool = True
    requires_confirmation: bool = False
    data_needs: dict[str, list[str | dict[str, Any]]] = Field(default_factory=dict)
    services: list[str] = Field(default_factory=list)


class WikiContextSnippet(BaseModel):
    source_type: str = "catalog_wiki"
    source_file: str | None = None
    page_title: str | None = None
    section_title: str | None = None
    content: str = ""
    score: float | None = None


class ContextValidation(BaseModel):
    status: Literal["valid", "invalid", "partial"] = "valid"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentContextPack(BaseModel):
    """Shared context passed to all workflows (spec §13)."""

    conversation_id: str
    run_id: str
    user_id: str
    intent: AgentIntent
    entities: dict[str, Any] = Field(default_factory=dict)
    user_context: dict[str, Any] = Field(default_factory=dict)
    academic_context: dict[str, Any] = Field(default_factory=dict)
    retrieved_wiki_context: list[WikiContextSnippet] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    validation: ContextValidation = Field(default_factory=ContextValidation)
    message_attachments: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_profile: str | None = None
    retrieval_profiles: list[str] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredBlock(BaseModel):
    type: BlockType | str
    data: dict[str, Any] = Field(default_factory=dict)


class ProposedAction(BaseModel):
    id: str
    action_type: str
    label: str
    title: str | None = None
    description: str | None = None
    preview: dict[str, Any] | None = None
    requires_confirmation: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "confirmed", "rejected", "expired"] = "pending"


class AgentResponse(BaseModel):
    """Final assistant payload (spec §29)."""

    conversation_id: str
    message_id: str
    run_id: str
    text: str
    blocks: list[StructuredBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_prompts: list[str] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    used_sources: list[str] = Field(default_factory=list)


class StreamEvent(BaseModel):
    type: StreamEventType
    label: str | None = None
    text: str | None = None
    block: StructuredBlock | None = None
    action: ProposedAction | None = None
    run_id: str | None = Field(default=None, serialization_alias="runId")
    message_id: str | None = Field(default=None, serialization_alias="messageId")
    error: str | None = None

    model_config = {"populate_by_name": True}

    def to_sse_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, by_alias=True)
