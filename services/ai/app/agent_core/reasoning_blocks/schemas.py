"""Shared schema shapes for the `BaseReasoningBlock` hierarchy (AGENT_VISION.md §6.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMCallParameters(BaseModel):
    """Per-invocation generation knobs that vary per component/role (§6.2):
    e.g. "Retrieval wants a cheap, fast, low-temperature model", "Calculation
    wants... temperature at or near zero". Every field defaults to `None`,
    meaning "fall back to the contract's/adapter's own default" -- never a
    hardcoded global.

    `timeout`/`max_retries` exist so one component (e.g. the Planner) can
    set its own request-level bound without affecting any other component's
    calls -- `None` here means "use the adapter's own default," exactly like
    every other field. Deliberately still excludes `max_tokens`/`top_p`: no
    evidenced per-role need for those yet, so they're not added as
    speculative surface.
    """

    model: str | None = None
    temperature: float | None = None
    thinking_enabled: bool | None = None
    reasoning_effort: str | None = None
    timeout: float | None = None
    max_retries: int | None = None


class BaseReasoningBlockInput(BaseModel):
    """Common floor every concrete reasoning block's own Input extends.

    Shape-specific fields (iteration caps, tool grants, persona rosters, ...)
    belong on each subclass's own Input, never here.
    """

    block_id: str
    agent_name: str
    objective: str
    task_context: dict[str, Any] = Field(default_factory=dict)
    output_schema_name: str
    output_schema: dict[str, Any]
    prompt_contract_name: str | None = None
    llm_call_parameters: LLMCallParameters = Field(default_factory=LLMCallParameters)


class BaseReasoningBlockOutput(BaseModel):
    """Common floor every concrete reasoning block's own Output extends.

    `status` is deliberately a loose `str`, not a shared `Literal` --
    e.g. "needs_tool" only means something for a tool-using shape. Each
    subclass defines its own narrower status vocabulary.
    """

    status: str
    schema_valid: bool
    result: dict[str, Any] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    total_llm_calls_used: int = 0


__all__ = [
    "LLMCallParameters",
    "BaseReasoningBlockInput",
    "BaseReasoningBlockOutput",
]
