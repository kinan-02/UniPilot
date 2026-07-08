"""The fixed, non-generative 5-role specialist roster's typed shape
(docs/agent/AGENT_VISION.md §6, §6.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from app.agent_core.planning.schemas import RoleName


class RoleReasoningDefaults(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    min_iterations: int
    max_iterations: int
    temperature: float
    model_name: str | None = None  # None = service default model


class RoleDefinition(BaseModel):
    name: RoleName
    prompt_contract_name: str
    tool_grant_ceiling: tuple[str, ...] = ()  # subset of ToolRegistry names; () for composition
    default_reasoning_params: RoleReasoningDefaults
    guardrails: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _composition_has_no_tools(self) -> "RoleDefinition":
        if self.name == "composition" and self.tool_grant_ceiling:
            raise ValueError("composition role must not carry any tool grant")
        return self


__all__ = ["RoleReasoningDefaults", "RoleDefinition"]
