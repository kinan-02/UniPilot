"""MAS agent turn types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentAction = Literal["propose", "critique", "veto", "revise", "commit"]


class AgentTurn(BaseModel):
    agent_role: str
    action: AgentAction
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    references: list[str] = Field(default_factory=list)


class PlanProposal(BaseModel):
    course_ids: list[str] = Field(default_factory=list)
    semester_filename: str | None = None
    notes: str = ""
    variant: str = "primary"


class NegotiationResult(BaseModel):
    status: Literal["completed", "failed", "awaiting_clarification"]
    final_decision: dict[str, Any] | None = None
    utility_breakdown: dict[str, Any] | None = None
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    rounds: int = 0
    error: str | None = None
