"""Schemas for proactive watchdog recommendations (AGT-8)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WatchdogNudgeType = Literal["pace", "prereq", "risk"]
WatchdogTrigger = Literal["profile_change", "new_plan", "weekly_cron"]
RecommendationStatus = Literal["active", "dismissed"]


class AiRecommendationPublic(BaseModel):
    id: str
    type: str = Field(serialization_alias="type")
    trigger: str
    severity: str
    title: str
    body: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    plan_id: str | None = Field(default=None, serialization_alias="planId")
    risk_analysis_id: str | None = Field(default=None, serialization_alias="riskAnalysisId")
    dedupe_key: str = Field(serialization_alias="dedupeKey")
    status: RecommendationStatus
    created_at: str | None = Field(default=None, serialization_alias="createdAt")
    updated_at: str | None = Field(default=None, serialization_alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class DismissRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
