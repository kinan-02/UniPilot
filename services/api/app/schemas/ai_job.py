"""Schemas for async AI jobs (AGT-1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AiJobType = Literal["advisor_deep_plan", "simulation_run", "watchdog_scan"]
AiJobStatus = Literal["pending", "processing", "completed", "failed"]


class AdvisorDeepPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    include_agent_trace: bool = False


class SimulationRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)


class WatchdogScanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    trigger: Literal["profile_change", "new_plan", "weekly_cron"] = "profile_change"
    plan_id: str | None = Field(default=None, alias="planId")


class CreateAiJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AiJobType
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload_for_type(self) -> CreateAiJobRequest:
        if self.type == "advisor_deep_plan":
            AdvisorDeepPlanPayload.model_validate(self.payload)
        if self.type == "simulation_run":
            SimulationRunPayload.model_validate(self.payload)
        if self.type == "watchdog_scan":
            WatchdogScanPayload.model_validate(self.payload)
        return self


class AiJobPublic(BaseModel):
    id: str
    type: str
    status: AiJobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = Field(default=None, serialization_alias="createdAt")
    updated_at: str | None = Field(default=None, serialization_alias="updatedAt")
    started_at: str | None = Field(default=None, serialization_alias="startedAt")
    finished_at: str | None = Field(default=None, serialization_alias="finishedAt")

    model_config = ConfigDict(populate_by_name=True)
