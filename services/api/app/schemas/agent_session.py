"""Pydantic schemas for MAS agent sessions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentSessionType = Literal["next_semester_plan"]
AgentSessionStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
    "awaiting_clarification",
]


class CreateAgentSessionRequest(BaseModel):
    type: AgentSessionType = "next_semester_plan"
    goal: str = Field(min_length=1, max_length=2000)
    constraints: dict[str, Any] = Field(default_factory=dict)


class OverrideAgentSessionRequest(BaseModel):
    course_ids: list[str] = Field(min_length=1, max_length=24)


class ClarifyAgentSessionRequest(BaseModel):
    clarification: str = Field(min_length=1, max_length=2000)


class WhyAgentSessionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class SecondOpinionAgentSessionRequest(BaseModel):
    utility_profile: Literal["balanced", "risk_averse", "aggressive"] = "balanced"


class ApplyAgentSessionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class AgentSessionResponse(BaseModel):
    id: str
    type: str
    goal: str
    status: AgentSessionStatus
    finalDecision: dict[str, Any] | None = None
    overriddenDecision: dict[str, Any] | None = None
    utilityBreakdown: dict[str, Any] | None = None
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    rounds: int = 0
    error: str | None = None
    approvedAt: str | None = None
    appliedAt: str | None = None
    appliedPlanId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
