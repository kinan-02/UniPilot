"""Lightweight request-body shape for the `agent` service's internal computation calls.

`graduation_audit_service` and `semester_planning_service` used to accept the
full `app.agent.schemas.AgentContextPack` in-process. Now that `app/agent/`
lives in its own service, this model carries just the handful of fields
those two functions actually read (`intent`, `entities`, `user_context`,
`assumptions`, `validation.warnings`) across the wire — the attribute access
patterns in those functions (`context.entities.get(...)`,
`context.user_context.get("profile")`, `context.validation.warnings`) work
unchanged against this model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentContextValidationSnapshot(BaseModel):
    status: str = "valid"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AgentContextSnapshot(BaseModel):
    intent: str
    entities: dict[str, Any] = Field(default_factory=dict)
    user_context: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    validation: AgentContextValidationSnapshot = Field(default_factory=AgentContextValidationSnapshot)
