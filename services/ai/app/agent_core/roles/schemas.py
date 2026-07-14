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
    # Per-call ceiling for this role's own reasoning-block calls (threaded
    # into `ReasoningBlockInput.timeout` by `subagents/builder.py`). Without
    # this, every specialist-role call fell through to the LLM adapter's own
    # much larger default timeout -- the same gap that caused a real 8+
    # minute live turn hang before any of these roles had one set.
    timeout: float | None = None


class RoleDefinition(BaseModel):
    name: RoleName
    prompt_contract_name: str
    tool_grant_ceiling: tuple[str, ...] = ()  # subset of ToolRegistry names; () for composition
    default_reasoning_params: RoleReasoningDefaults
    guardrails: tuple[str, ...] = ()
    # A concise, routing-facing statement of what this specialist DOES and,
    # crucially, what it CANNOT do (and which specialist it hands off to). The
    # Specialist Router's capability catalog is rendered from this field + the
    # tool grant above, so the router's model of the roster is structurally
    # incapable of drifting from the roster itself (see roles/catalog.py). Kept
    # here, on the single source of truth, rather than in a hand-maintained
    # prompt paragraph. Defaults to empty so ad-hoc RoleDefinitions in tests
    # need not supply it; the real roster fills every role (guarded by
    # tests/agent_core/test_roles.py).
    routing_capability: str = ""

    @model_validator(mode="after")
    def _composition_has_no_tools(self) -> "RoleDefinition":
        if self.name == "composition" and self.tool_grant_ceiling:
            raise ValueError("composition role must not carry any tool grant")
        return self


__all__ = ["RoleReasoningDefaults", "RoleDefinition"]
